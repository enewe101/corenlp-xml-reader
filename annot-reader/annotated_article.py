from collections import Counter
import json
import re
from bs4 import BeautifulSoup as Soup
import time

class AnnotatedArticleException(Exception):
	pass

class AnnotatedArticle(object):

	MATCH_TAG = re.compile(r'^\((\S+)\s*')
	MATCH_END_BRACKET = re.compile(r'\s*\)\s*$')
	MATCH_TEXT_ONLY = re.compile(r'^[^)(]*$')

	EXCLUDE_NER_TYPES = set([
		'TIME', 'DATE', 'NUMBER', 'DURATION', 'PERCENT', 'SET', 'ORDINAL',
		'MONEY'
	])

	def __init__(
		self, 
		stanford_xml=None, 
		aida_json=None,
		dependencies='collapsed-ccprocessed',
		exclude_ordinal_NERs=False
	):

		# If true, do not include NER's of the types listed in 
		# EXCLUDE_NER_TYPES
		self.exclude_ordinal_NERs = exclude_ordinal_NERs

		# do some validation on dependencies
		if dependencies not in [
			'collapsed-ccprocessed', 'collapsed', 'basic'
		]:
			raise ValueError(
				'dependencies must be one of "basic", '
				'"collapsed", or "collapsed-ccprocessed".'
			)
		
		self.dependencies = dependencies

		# parse the annotated article xml
		if stanford_xml is not None:
			self.read_stanford_xml(stanford_xml)
			if aida_json is not None:
				self.read_aida_json(aida_json)

		elif aida_json is not None:
			raise ValueError(
				'You provide AIDA json without also providing Stanford'
				' xml.'
			)


	def read_stanford_xml(self, article_string):
		'''
			read in an article that has been annotated by coreNLP, and
			represent it using python objects
		'''

		# a string representing the xml output by coreNLP
		self.text = article_string

		# The <head></head> tags don't get red correctly, turn them into 
		# <headword> instead
		head_replacer =  re.compile(r'(?P<open_tag></?)\s*head\s*>')  
		self.text = head_replacer.sub('\g<open_tag>headword>', self.text)

		# Parse the xml
		self.soup = Soup(self.text, 'html.parser')
		
		# First sentence null to match coreNLP numbering
		self.sentences = [Sentence({'id':0})]	
		self.tokens_by_offset = {}
		self.tokens = []

		# Read all the sentences
		self.num_sentences = 0
		try:
			for s in self.soup.find('sentences').find_all('sentence'):
				self.num_sentences += 1
				self.sentences.append(self.read_sentence(s))

		# Tolerate an article having no sentences
		except AttributeError:
			pass

		# build the coreferences
		self.coreferences = self.read_corefs(self.soup.find('coreference'))

		# now that we have entities from NER and from coreferences
		# we want to eliminate redundancies between them
		self.references = self.merge_references(
			self.sentences, self.coreferences)

		self.link_references()

		print 'hot and fresh'


	def read_aida_json(self, json_string):

		# read the file
		aida_data = json.loads(json_string)

		# tie each mention disambiguated by aida to a corresponding mention
		# in the stanford output
		for aida_mention in aida_data['mentions']:
			self.link_aida_mention(aida_mention, aida_data)

		# For each referenece (group of mentions believed to refer to the
		# same entity) check for inconsistent entities
		self.disambiguated_references = []
		for reference in self.references:
			self.link_aida_reference(reference, aida_data)


	def link_aida_reference(self, reference, aida_data):

			# Tally up the kbids that have been attached mentions within 
			# this reference
			kbid_counter = Counter()
			kbid_score_tally = Counter()
			for mention in reference['mentions']:
				try:
					kbid_counter[mention['kbIdentifier']] += 1
					kbid_score_tally[mention['kbIdentifier']] += mention[
						'disambiguationScore']
				except KeyError:
					pass

			# Sort the kbids based on the number of times a mention
			# was linked to that kbid
			kbids_by_popularity = kbid_counter.most_common()

			# Fail if no kbids were linked to mentions in this reference
			if len(kbids_by_popularity) == 0:
				return

			# Pull out those kbids that received the most votes
			majority_num_votes = kbids_by_popularity[0][1]
			majority_vote_kbids = [
				kbid for kbid, count 
				in kbids_by_popularity
				if count == majority_num_votes
			]

			# Sort them by largest total confidence score to break ties
			score_tallied_kbids = sorted([
				(kbid_score_tally[kbid], kbid)
				for kbid in majority_vote_kbids
			], key=lambda x: x[0])

			# Assign the highest confidence kbid to the reference
			# Also, decode any escaped unicode
			kbId = score_tallied_kbids[0][1]
			reference['kbIdentifier'] = kbId

			# Assign the YAGO taxonomy types associated to that entity
			# Remove the "YAGO_" at the same time.
			reference['types'] = [
				t[len('YAGO_'):] for t in 
				aida_data['entityMetadata'][kbId]['type']
			]

			# Add this reference to the list of disambiguated references
			self.disambiguated_references.append(reference)


	def link_aida_mention(self, aida_mention, aida_data):

		# take the best matched entity found by AIDA for this mention
		try:
			kbid = (
				aida_mention['bestEntity']['kbIdentifier']
				.decode('unicode-escape')
			)
			score = float(aida_mention['bestEntity']['disambiguationScore'])
			# Assign the YAGO taxonomy types.  Remove the "YAGO_" prefix
			# from them at the same time.
			types = [
				t[len('YAGO_'):] for t in 
				aida_data['entityMetadata'][kbid]['type']
			]


		# Fail if AIDA provided no entity
		except KeyError:
			return 

		# Find the corresponding Stanford-identified mention
		mention = self.find_or_create_mention_by_offset_range(
			aida_mention['offset'], aida_mention['length'])

		# fail if no associated mention could be found:
		if mention is None:
			return

		mention['kbIdentifier'] = kbid
		mention['disambiguationScore'] = score
		mention['types'] = types


	def find_or_create_mention_by_offset_range(self, start, length):

		pointer = start
		mention = None
		found_tokens = []
		while pointer <= start + length:

			# find the next token
			token = self.get_token_after(pointer)

			# handle an edge case where a token that goes beyond the 
			# the range is inadvertently accessed
			if token['endIndex'] > start + length:
				break

			# Add the token to the list of spanned tokens
			found_tokens.append(token)

			# find the mention related to that token, if any
			try:
				mention = token['mention']
				break
			except KeyError:
				pass

			pointer = token['endIndex']

		# If no tokens associated with the mention are found 
		# (a zero-token mention?), fail
		if len(found_tokens) == 0:
			return None

		# If we found an existing mention, return it
		if mention is not None:
			return mention

		# Otherwise, create a mention
		# Need to add ref to self.references
		#
		# make the mention
		sentence_id = found_tokens[0]['sentence_id']
		sentence = self.sentences[sentence_id]
		new_mention = {
			'tokens': found_tokens,
			'start': min([t['id'] for t in found_tokens]),
			'end': max([t['id'] for t in found_tokens]),
			'head': self.find_head(found_tokens),
			'sentence_id': sentence_id,
			'sentence': sentence
		}
		ref = {
			'id': self.get_next_coref_id(),
			'mentions': [new_mention],
			'representative': new_mention
		}
		new_mention['reference'] = ref
		self.references.append(ref)

		# Add the mention to the sentence
		try:
			sentence['mentions'].append(new_mention)
		except KeyError:
			sentence['mentions'] = [new_mention]

		# Add the mention to the tokens involved
		for token in found_tokens:
			token['mention'] = new_mention

		# Add the reference to the sentence
		try:
			sentence['references'].append(ref)
		except KeyError:
			sentence['references'] = [ref]

		return new_mention


	def get_token_after(self, pointer):
		token = None
		while token is None:

			# Get the token at or after offset <pointer>
			try:
				token = self.tokens_by_offset[pointer]
			except KeyError:
				pointer += 1

				# But if we reach the end of the text it's an error
				if pointer > len(self.text):
					raise

		return token



	def get_next_coref_id(self):
		'''
			yield incrementing coreference ids.
		'''
		try:
			self.next_coref_id += 1
		except AttributeError:
			self.next_coref_id = 1

		return self.next_coref_id - 1


	def link_references(self):
		'''
			once NER-groups and coreference chains have been merged into 
			a standard "reference" type based on mentions, create a link 
			from each mention's tokens back to the mention, and create a 
			link from the sentence to the entities for which it has 
			mentions.
		'''

		for ref in self.references:
			for mention in ref['mentions']:

				# link the mention to its reference
				mention['reference'] = ref

				# link the tokens to the mention
				for token in mention['tokens']:
					token['mention'] = mention

				# note the extent of the mention
				mention['start'] = min([t['id'] for t in mention['tokens']])
				mention['end'] = max([t['id'] for t in mention['tokens']])

				# link the sentence to the mention
				mention_sentence_id = mention['tokens'][0]['sentence_id']
				sentence = self.sentences[mention_sentence_id]
				try:
					sentence['mentions'].append(mention)
				except KeyError:
					sentence['mentions'] = [mention]

			# git all the sentences (by id) for a given reference
			ref_sentence_ids = set([
				token['sentence_id']
				for mention in ref['mentions']
				for token in mention['tokens']
			])

			# link the sentence to the references
			for s_id in ref_sentence_ids:
				sentence = self.sentences[s_id]
				try:
					sentence['references'].append(ref)
				except KeyError:
					sentence['references'] = [ref]


	def merge_references(self, sentences, coreferences):

		# gather together id-signature representing all entities from NER
		all_ner_signatures = set()
		ner_entity_lookup = {}

		for s in sentences[1:]:
			for entity in s['entities']:

				# the sentence id and id of the entities head token 
				# uniquely identifies it, and is hashable
				entity_signature = (
					entity['sentence_id'], 	# idx of the sentence
					entity['head']['id'],	# idx of entity's head token
					#entity['head']['word'] # debug
				)

				# keep a link back to the entity based on its signature
				ner_entity_lookup[entity_signature] = entity

				all_ner_signatures.add(entity_signature)

		all_coref_signatures = set()
		coref_entity_lookup = {}
		all_mention_signatures = set()
		all_coref_tokens = set()
		# gather together id-signature representing all entities from coref
		for coref in coreferences:

			coref_signature = (
				coref['representative']['sentence_id'],
				coref['representative']['head']['id'],
			)

			coref_entity_lookup[coref_signature] = coref
			all_coref_signatures.add(coref_signature)

			for mention in coref['mentions']:

				all_coref_tokens.update([
					(mention['sentence_id'], t['id'])
					for t in mention['tokens']
				])

				all_mention_signatures.add((
					mention['sentence_id'],
					mention['head']['id'],
				))

		# get the ner signatures which aren't yet among the coref mentions
		novel_ner_signatures = all_ner_signatures - all_coref_tokens

		# get the coref signatures that are actual ners
		valid_coref_signatures = all_coref_signatures & all_ner_signatures

		# The corefs that are ners are valid and already assembled, copy 
		# them
		valid_refs = [
			coref_entity_lookup[es] for es in valid_coref_signatures
		]

		# build the ners not yet among the corefs into same structure as 
		# corefs
		for signature in novel_ner_signatures:
			entity = ner_entity_lookup[signature]
			valid_refs.append({
				'id':self.get_next_coref_id(),
				'mentions': [entity],
				'representative': entity
			})

		return valid_refs


	def read_corefs(self, all_coreferences_tag):

		if all_coreferences_tag is None:
			return []

		coreference_tags = all_coreferences_tag.find_all('coreference')
		coreferences = []
		for ctag in coreference_tags:

			coreference = {
				'id': self.get_next_coref_id(),
				'mentions':[],
			}

			for mention_tag in ctag.find_all('mention'):

				sentence_id = int(mention_tag.find('sentence').text)
				sentence = self.sentences[sentence_id]
				start = int(mention_tag.find('start').text)
				end = int(mention_tag.find('end').text)
				head = int(mention_tag.find('headword').text)

				mention = {
					'sentence_id': sentence_id,
					'tokens': sentence['tokens'][start:end],
					'head': sentence['tokens'][head]
				}

				# long mentions are typically nonsense
				if len(mention['tokens']) > 5:
					continue

				if 'representative' in mention_tag.attrs:
					coreference['representative'] = mention

				coreference['mentions'].append(mention)

			# if there's no mentions left in the coreference, don't keep it
			if len(coreference['mentions']) < 1:
				continue

			# if we didn't assign a representative mention, do it now
			if 'representative' not in coreference:
				coreference['representative'] = coreference['mentions'][0]

			coreferences.append(coreference)

		return coreferences


	def filter_mention_tokens(self, tokens):
		tokens_with_ner = [t['ner'] is not None for t in tokens]
		try: 
			idx_at_first_ner_token = tokens_with_ner.index(True)
			idx_after_last_ner_token = (
				len(tokens_with_ner)
				- list(reversed(tokens_with_ner)).index(True)
			)

		except ValueError:
			return []

		return tokens[idx_at_first_ner_token:idx_after_last_ner_token]

	

	def print_dep_tree(self, root_token, depth):
		depth += 1
		if 'children' in root_token:
			for relation, child in root_token['children']:
				print '\t'*depth + relation + ' ' + child['word']
				self.print_dep_tree(child, depth)




	def print_tree(self, tree):
		if len(tree['children']) == 0:
			print '\n'+('\t'*tree['depth'])+tree['code']+ ' : ' + tree['word']

		else:
			print '\n' + ('\t'*tree['depth'])+tree['code']+ ' :'
			for child in tree['children']:
				self.print_tree(child)


	def read_sentence(self, sentence_tag):
		'''
			convert sentence tags to python dictionaries
		'''
		sentence =  Sentence({
			'id': int(sentence_tag['id']),
			'tokens': self.read_tokens(sentence_tag),
			#'parse': self.read_parse(sentence_tag.find('parse').text),
		})

		# give the tokens the dependency tree relation
		self.read_dependencies(sentence, sentence_tag, self.dependencies)

		# Group the named entities together, and find the headword within
		sentence['entities'] = self.read_entities(sentence['tokens'])

		# Add tokens to global list and to the token offset-lookup table
		# Exclude the "null" tokens that simulate sentence head.
		self.tokens.extend(sentence['tokens'][1:])
		token_offsets = dict([
			(t['beginIndex'], t) for t in sentence['tokens'][1:]
		])
		self.tokens_by_offset.update(token_offsets)

		return sentence


	def read_dependencies(self, sentence, sentence_tag, dependencies):

		if dependencies == 'collapsed-ccprocessed':
			dependencies_type = 'collapsed-ccprocessed-dependencies'
		elif dependencies == 'collapsed':
			dependencies_type = 'collapsed-dependencies'
		elif dependencies == 'basic':
			dependencies_type = 'basic-dependencies'
		else:
			raise ValueError(
				'dependencies must be one of "basic", '
				'"collapsed", or "collapsed-ccprocessed".'
			)

		dependencies = sentence_tag.find(
			'dependencies', type=dependencies_type
		).find_all('dep')


		for dep in dependencies:
			governor_idx = int(dep.find('governor')['idx'])
			governor = sentence['tokens'][governor_idx]

			dependent_idx = int(dep.find('dependent')['idx'])
			dependent = sentence['tokens'][dependent_idx]

			# refuse to add a link which would create a cycle 
			if governor_idx in self.collect_descendents(dependent):
				continue

			dep_type = dep['type']
		
			try:
				governor['children'].append((dep_type, dependent))
			except KeyError:
				governor['children'] = [(dep_type, dependent)]

			try:
				dependent['parents'].append((dep_type, governor))
			except KeyError:
				dependent['parents'] = [(dep_type, governor)]


	def collect_descendents(self, token):

		descendents = [token['id']]

		if 'children' not in token:
			return descendents

		for dep_type, child in token['children']:
			descendents += self.collect_descendents(child)

		return descendents
			


	def read_parse(self, parse_text, parent=None, depth=0):

		element = {'depth':depth}

		# get the phrase or POS code
		element['code'] = self.MATCH_TAG.match(parse_text).groups()[0]

		# get the inner text
		inner_text = self.MATCH_TAG.sub('', parse_text)
		inner_text = self.MATCH_END_BRACKET.sub('', inner_text)

		# if the inner text is just a word, get it, and don't recurse
		if self.MATCH_TEXT_ONLY.match(inner_text):
			element['word'] = inner_text.strip()
			element['children'] = []
			

		# if the inner text encodes child nodes, parse them recursively
		else: 
			element['word'] = None
			child_texts = self.split_parse_text(inner_text)
			element['children'] = [
				self.read_parse(ct, element, depth+1) for ct in child_texts]

		element['parent'] = parent

		return element


	def split_parse_text(self, text):
		if text[0] != '(':
			raise ValueError('expected "(" at begining of sentence node.')

		depth = 0
		strings = []
		curstring = ''
		for c in text:

			# skip whitespace between nodes
			if depth == 0 and c.strip() == '':
				continue

			curstring += c
			if c == '(':
				depth += 1
			if c == ')':
				depth -= 1

			if depth == 0:
				strings.append(curstring)
				curstring = ''

		return strings


	def read_entities(self, tokens):
		'''
			collect the entities into a mention-like object
		'''

		entities = []
		last_entity_type = None
		cur_entity = None
		entity_idx = -1

		for token in tokens[1:]:	# skip the root token

			exclude = False
			if self.exclude_ordinal_NERs:
				if token['ner'] in self.EXCLUDE_NER_TYPES:
					exclude = True

			if token['ner'] is None or exclude:
				token['entity_idx'] = None

				# this might be the end of an entity
				if cur_entity is not None:
					entities.append(cur_entity)
					cur_entity = None

			elif token['ner'] == last_entity_type:
				cur_entity['tokens'].append(token)
				token['entity_idx'] = entity_idx

			else:
				# begins a new entity.  Possibly ends an old one
				if cur_entity is not None:
					entities.append(cur_entity)
					cur_entity = None

				entity_idx += 1
				cur_entity = {
					'tokens':[token], 
					'sentence_id': int(token['sentence_id'])
				}
				token['entity_idx'] = entity_idx

			last_entity_type = token['ner']


		# if sentence end coincides with entity end, be sure to add entity
		if cur_entity is not None:
			entities.append(cur_entity)

		# Now that we have the entities, find the headword for each
		for entity in entities:
			entity['head'] = self.find_head(entity['tokens'])

		# filter out entities that have no head
		entities = [e for e in entities if e['head'] is not None]

		return entities


	def find_head(self, tokens):

		head = None

		# If there is only one token, that's the head
		if len(tokens) ==  1:
			head = tokens[0]

		else:

			# otherwise iterate over all the tokens to find the head
			for token in tokens:

				# if this token has no parents or children its not part
				# of the dependency tree (it's a preposition, e.g.)
				if 'parents' not in token and 'children' not in token:
					continue

				# if this token has any parents that among the tokens list
				# it's not the head!
				try:
					if any([t[0] in tokens for t in token['parents']]):
						continue
				except KeyError:
					pass

				# otherwise it is the head
				else:
					head = token

		#if head is None:
		#	print [t['word'] for t in tokens]
		#	sentence_id = tokens[0]['sentence_id']
		#	print sentence_id
		#	raise AnnotatedArticleException(
		#		'Could not find the head of the token list'
		#	)

		# NOTE: head may be none
		return head


	def read_tokens(self, sentence_tag):
		'''
			convert token tag to python dictionary
		'''

		# include a root token, which becomes root of the dependency tree
		tokens = [Token({'id':0,'word':'ROOT'})]
		sentence_id = sentence_tag['id']

		for token_tag in sentence_tag.find_all('token'):
			try:
				token = Token({
					'id': int(token_tag['id']),
					'sentence_id': int(sentence_id),
					'word': self.fix_word(token_tag.find('word').text),
					'lemma': token_tag.find('lemma').text,
					'pos': token_tag.find('pos').text,
					'ner': (
						None if token_tag.find('ner').text == 'O' 
						else token_tag.find('ner').text),
					'beginIndex': int(
						token_tag.find('characteroffsetbegin').text),
					'endIndex': int(
						token_tag.find('characteroffsetend').text),
				})
			except AttributeError:
				print token_tag

			tokens.append(token)

		return tokens

	def fix_word(self, word):
		if word == '-LRB-':
			return '('
		if word == '-RRB-':
			return ')'
		#if word == 'Howerd':
		#	print '\n\n\n\n\n****** gotcha'
		#	raise ValueError

		return word#.encode('utf8').decode('unicode-escape')


	def __str__(self):
		string = ''
		for s in self.sentences:
			string +=  str(s) + '\n'

		return string
				
				



class Sentence(dict):

	def __init__(self, *args, **kwargs):
		super(Sentence, self).__init__(*args, **kwargs)
		mandatory_listy_attributes = [
			'tokens', 'entities', 'references', 'mentions']
		for attr in mandatory_listy_attributes:
			if attr not in self:
				self[attr] = []

	def as_string(self):
		'''
			return a simple single-line string made from all the tokens in 
			the sentence.  This is basically the way the sentence actually 
			occurred in the text, but whitespace and certain punctuation get
			normalized.
		'''
		# note, the first token is a "root token", which has to be skipped
		return ' '.join([t['word'] for t in self['tokens'][1:]])


	def __repr__(self):
		if 'tokens' not in self:
			return '%d: (null sentence)' % self['id']

		return(
			'<Sentence %d: ' % self['id'] 
			+ ' '.join([t['word'] for t in self['tokens'][1:]]) + '>'
		)


	def __str__(self):
		if 'tokens' not in self:
			return 'S#:%d (null sentence)\n' % self['id']

		string = 'S%d\n' % self['id']

		for t in self['tokens']:
			string += '\t%s\n' % str(t)

		return string


	def shortest_path(self, source, target):
		'''
			find the shortest path between source and target by performing a
			breadth first from source, until target is seen
		'''

		source_node = {'id': source['id'], 'prev':None, 'next':[]}

		ptr = 0
		queue = [source_node]
		seen = set([source['id']])
		path = None

		while ptr < len(queue):

			cur_node = queue[ptr]
			cur_token = self['tokens'][cur_node['id']]


			if cur_node['id'] == target['id']:
				path = self.trace_back(cur_node)
				break
			
			next_tokens = cur_token.get_children() + cur_token.get_parents()


			for relation, next_token in next_tokens:

				if next_token['id'] in seen:
					continue

				seen.add(next_token['id'])
				next_node = {'id':next_token['id'], 'prev':cur_node, 'next':[]}
				cur_node['next'].append(next_node)
				queue.append(next_node)

			#print 'ptr', ptr
			#print 'at token', cur_token['word']
			#print 'added tokens:', [t['word'] for r,t in next_tokens]
			#print len(queue)
			#print 

			ptr += 1

		if path is None:
			return path

		# path is a list of token ids.  Convert it to list of actual tokens
		path = [self['tokens'][i] for i in path]

		return path


	def trace_back(self, target):
		path = [target['id']]
		cur = target

		while cur['prev'] is not None:
			cur = cur['prev']
			path.append(cur['id'])

		path.reverse()
		return path


	def dep_tree_str(self):
		if 'tokens' not in self:
			return ''

		return self._dep_tree_str(self['tokens'][0])


	def get_text(self):
		return ' '.join([t['word'] for t in self['tokens']])


	def _dep_tree_str(self, root_token, depth=0):
		depth += 1
		string = ''

		if 'children' in root_token:
			for relation, child in root_token['children']:
				string +=  (
					'\t'*depth + '<' + relation + '> ' + str(child) + '\n')
				string += self._dep_tree_str(child, depth)

		return string


class Token(dict):

	def __str__(self):

		try:
			ner = '-' if self['ner'] is None else self['ner']
			return 'T%d %s [%s] (%s)' % (
				self['id'], self['word'], self['pos'], ner)

		except KeyError:
			return 'T%d %s' % (self['id'], self['word'])


	def get_parents(self):
		return self['parents'] if 'parents' in self else []


	def get_children(self):
		return self['children'] if 'children' in self else []


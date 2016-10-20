from collections import Counter
import json
import re
from bs4 import BeautifulSoup as Soup
import time

class AnnotatedTextException(Exception):
	pass

class AnnotatedText(object):

	MATCH_TAG = re.compile(r'^\((\S+)\s*')
	MATCH_END_BRACKET = re.compile(r'\s*\)\s*$')
	MATCH_TEXT_ONLY = re.compile(r'^[^)(]*$')

	EXCLUDE_NER_TYPES = set([
		'TIME', 'DATE', 'NUMBER', 'DURATION', 'PERCENT', 'SET', 'ORDINAL',
		'MONEY'
	])
	LEGAL_DEPENDENCY_TYPES = set([
		'collapsed-ccprocessed', 'collapsed', 'basic'
	])

	def __init__(
		self, 
		corenlp_xml=None, 
		aida_json=None,
		dependencies='collapsed-ccprocessed',
		exclude_ordinal_NERs=False,
		exclude_long_mentions=False,
		long_mention_threshold=5,
		exclude_non_ner_coreferences=False
	):

		# If true, do not include NER's of the types listed in 
		# EXCLUDE_NER_TYPES
		self.exclude_ordinal_NERs = exclude_ordinal_NERs

		# If true, ignore coreference mentions that are more than 
		# long_mention_threshold number of tokens long
		self.exclude_long_mentions = exclude_long_mentions
		self.long_mention_threshold = long_mention_threshold

		# If true, ignore coreference chains that don't have a Named Entity
		# as their representative mention.  
		self.exclude_non_ner_coreferences = exclude_non_ner_coreferences

		# User can choose the kind of dependency parse they wish to use
		# Valid options listed below.  Ensure that a valid option was 
		# chosen
		if dependencies not in self.LEGAL_DEPENDENCY_TYPES:
			raise ValueError(
				'dependencies must be one of "basic", '
				'"collapsed", or "collapsed-ccprocessed".'
			)
		
		self.dependencies = dependencies

		# Parse the annotated article xml
		if corenlp_xml is not None:
			self._read_stanford_xml(corenlp_xml)

			# Parse the AIDA JSON
			if aida_json is not None:
				self._read_aida_json(aida_json)

		# User cannot provide AIDA data unless stanford xml is also 
		# provided
		elif aida_json is not None:
			raise ValueError(
				'You provide AIDA json without also providing Stanford'
				' xml.'
			)


	def _read_stanford_xml(self, article_string):
		'''
		read in an article that has been annotated by coreNLP, and
		represent it using python objects
		'''

		# a string representing the xml output by coreNLP
		self.text = article_string

		# Parse the CoreNLP xml using BeautifulSoup
		self._beautiful_soup_parse()

		# Build a Python representation of all the sentences
		self._read_all_sentences()

		# build a Python representation of the coreference chains
		self._build_coreferences()

		# Link AIDA disambiguations to corresponding coreference chains
		self._link_references()


	def _beautiful_soup_parse(self):

		# Before parsing the xml, we have to deal with a glitch in how 
		# beatiful soup parses xml: it doesn't allow <head></head> tags, 
		# which do appear in CoreNLP output.  Work around this by converting
		# these into <headword> tags instead.
		head_replacer =  re.compile(r'(?P<open_tag></?)\s*head\s*>')  
		self.text = head_replacer.sub('\g<open_tag>headword>', self.text)

		# Parse the xml
		self.soup = Soup(self.text, 'html.parser')


	def _read_all_sentences(self):
		'''
		Process all of the sentence tags in the CoreNLP xml.  Each
		Sentence has tokens and a dependency parse.  Read tokens' 
		attributes into Python types, and add links between tokens 
		representing the dependency tree.
		'''

		# Initialize some containers to hold data found in sentences
		self.sentences = []	
		self.tokens = []
		self.tokens_by_offset = {}
		self.num_sentences = 0

		# Get all the sentence tags
		try:
			sent_tags = self.soup.find('sentences').find_all('sentence')

		# Tolerate an article having no sentences
		except AttributeError, e:
			sent_tags = []

		# Process each sentence tag
		for s in sent_tags:
			self.num_sentences += 1
			self.sentences.append(self._read_sentence(s))


	def _read_aida_json(self, json_string):

		# Parse the json
		aida_data = json.loads(json_string)

		# Tie each mention disambiguated by aida to a corresponding mention
		# in the stanford output
		for aida_mention in aida_data['mentions']:
			self._link_aida_mention(aida_mention, aida_data)

		# For each referenece (group of mentions believed to refer to the
		# same entity) check for inconsistent entities
		self.disambiguated_references = []
		for reference in self.references:
			self._link_aida_reference(reference, aida_data)


	def _link_aida_reference(self, reference, aida_data):

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
			# IDEA: would it be more expected to set kbid to None rather
			# than have it not exist at all?
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


	def _link_aida_mention(self, aida_mention, aida_data):

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
		mention = self._find_or_create_mention_by_offset_range(
			aida_mention['offset'], aida_mention['length'])

		# fail if no associated mention could be found:
		if mention is None:
			return

		mention['kbIdentifier'] = kbid
		mention['disambiguationScore'] = score
		mention['types'] = types


	def _find_best_mention_overlap(self, mentions, start, end):
		'''
		Given a list of `mentions`, find the one whose character offset 
		range which "best" matches the one defined by `start` and `length`.
		'''
		desired_range = (start, end)

		# Get the offset range for each mention
		mention_ranges = []
		for mention in mentions:
			start = mention['tokens'][0]['character_offset_begin']
			end = mention['tokens'][-1]['character_offset_end']
			mention_ranges.append((start, end))
		
		# Rate the coverage provided by each mention
		coverage_scores = [
			self._get_coverage_score(mention_range, desired_range)
			for mention_range in mention_ranges
		]

		# Find the mention with the best coverage score
		top_cover, top_mention = sorted(
			zip(coverage_scores, mentions), reverse=True
		)[0]

		return top_mention


	def _get_coverage_score(self, range1, range2):
		'''
		Computes the Jaccard overlap for two ranges of numbers.
		'''
		intersection_start = max(range1[0], range2[0])
		intersection_end = min(range1[1], range2[1])
		intersection_size = intersection_end - intersection_start

		union_start = min(range1[0], range2[0])
		union_end = max(range1[1], range2[1])
		union_size = union_end - union_start

		return intersection_size / float(union_size)


	def _find_or_create_mention_by_offset_range(self, start, length):

		pointer = start			# Character offset pointer in range
		found_tokens = []		# Accumulates all tokens in range
		mentions = []			# Accumulates all mentions in range
		seen_mentions = set()	# Prevent duplication during accumulation
		end = start + length	# Position after last character of range

		# Find all of the tokens falling inside the offset range,
		# and find all pre-existing mentions
		while pointer <= end:

			# find the next token
			token = self._get_token_after(pointer)

			# handle an edge case where a token that goes beyond the 
			# the range is inadvertently accessed
			if token['character_offset_end'] > end:
				break

			# Keep the token and its mentions
			found_tokens.append(token)
			for mention in token['mentions']:
				if (mention['start'], mention['end']) not in seen_mentions:
					mentions.append(mention)
					seen_mentions.add((mention['start'], mention['end']))

			# Move the pointer so we access the next token
			pointer = token['character_offset_end']

		# If there were no tokens found in the offset range, fail
		if len(found_tokens) == 0:
			return None

		# If exactly one mention was found, return it
		if len(mentions) == 1:
			return mentions[0]

		# If multiple entities were found, return the one that overlaps
		# most exactly with the AIDA mention
		elif len(mentions) > 0:
			return self._find_best_mention_overlap(mentions, start, end)

		# If no mention was found (but there were tokens in the indicated
		# range), then *create* a mention and reference with those tokens
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
			'id': self._get_next_coref_id(),
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
			token['mentions'].append(new_mention)

		# Add the reference to the sentence
		try:
			sentence['references'].append(ref)
		except KeyError:
			sentence['references'] = [ref]

		return new_mention


	def _get_token_after(self, pointer):
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



	def _get_next_coref_id(self):
		'''
		yield incrementing coreference ids.
		'''
		try:
			self.next_coref_id += 1
		except AttributeError:
			self.next_coref_id = 1

		return self.next_coref_id - 1


	def _link_references(self):
		'''
		Create a link from each mention's tokens back to the mention, and 
		create a link from the sentence to the entities for which it has 
		mentions.
		'''
		for ref in self.references:
			for mention in ref['mentions']:

				# link the mention to its reference
				mention['reference'] = ref

				# link the tokens to the mention
				for token in mention['tokens']:
					token['mentions'].append(mention)

				# note the extent of the mention
				mention['start'] = min(
					[t['id'] for t in mention['tokens']])
				mention['end'] = max([t['id'] for t in mention['tokens']])

				# link the sentence to the mention
				mention_sentence_id = mention['tokens'][0]['sentence_id']
				sentence = self.sentences[mention_sentence_id]
				try:
					sentence['mentions'].append(mention)
				except KeyError:
					sentence['mentions'] = [mention]

			# Get all the sentences (by id) for a given reference
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


	def _standardize_coreferencing(self):

		# Generate an identifying signature for each NER entity, which
		# will be used to cros-reference with coreference mentions.
		all_ner_signatures = set()
		ner_entity_lookup = {}
		for s in self.sentences:
			for entity in s['entities']:

				# the sentence id and id of the entity's head token 
				# uniquely identifies it, and is hashable
				entity_signature = (
					entity['sentence_id'], 	# idx of the sentence
					entity['head']['id'],	# idx of entity's head token
				)
				all_ner_signatures.add(entity_signature)

				# keep a link back to the entity based on its signature
				ner_entity_lookup[entity_signature] = entity

		# Generate an identifying signature for each coreference and for
		# each mention.  We will then be able to cross-reference the 
		# coreference chains / mentions and the entities
		all_coref_signatures = set()
		coref_entity_lookup = {}
		all_mention_signatures = set()
		all_coref_tokens = set()
		for coref in self.coreferences:

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

		# In some cases, we want "coreferences" to mean only coreference
		# chains whose representative mention is a NER.  Otherwise,
		# we'll take all coreferences.  A coreference chain could, for 
		# example, refer to an entity mentioned several times using a
		# common noun (e.g. "the police").
		if self.exclude_non_ner_coreferences:
			self.references = [
				coref_entity_lookup[es] for es in valid_coref_signatures
			]
		else:
			self.references = [coref for coref in self.coreferences]

		# build the ners not yet among the corefs into same structure as 
		# corefs
		for signature in novel_ner_signatures:
			entity = ner_entity_lookup[signature]
			self.references.append({
				'id':self._get_next_coref_id(),
				'mentions': [entity],
				'representative': entity
			})


	def _build_coreferences(self):

		self.coreferences = []

		coref_tag_container = self.soup.find('coreference')
		if coref_tag_container is None:
			coreference_tags = []
		else:
			coreference_tags = coref_tag_container.find_all('coreference')

		for ctag in coreference_tags:

			coreference = {
				'id': self._get_next_coref_id(),
				'mentions':[],
			}

			# Process each mention in this coreference chain
			for mention_tag in ctag.find_all('mention'):

				# Recall that we convert 1-based ids to 0-based
				sentence_id = int(mention_tag.find('sentence').text) - 1
				sentence = self.sentences[sentence_id]
				start = int(mention_tag.find('start').text) - 1
				end = int(mention_tag.find('end').text) - 1
				head = int(mention_tag.find('headword').text) - 1

				mention = {
					'sentence_id': sentence_id,
					'tokens': sentence['tokens'][start:end],
					'head': sentence['tokens'][head]
				}

				# Long mentions are typically nonsense
				do_exclude = (
					self.exclude_long_mentions and 
					len(mention['tokens']) > self.long_mention_threshold
				)
				if do_exclude:
					continue

				if 'representative' in mention_tag.attrs:
					coreference['representative'] = mention

				coreference['mentions'].append(mention)

			# if there's no mentions left in the coreference, don't keep it
			# (this can happen if we are excluding long mentions.)
			if len(coreference['mentions']) < 1:
				continue

			# if we didn't assign a representative mention, assign it to
			# the first mention
			if 'representative' not in coreference:
				coreference['representative'] = coreference['mentions'][0]

			self.coreferences.append(coreference)

		# When a named entity gets referred to only once, CoreNLP doesn't
		# make a coreference chain for that named entity.  This makes 
		# scripts more complicated.  Things are simplified if all NERs are
		# guaranteed to have a coreference chain representation, even if
		# some "chains" contains only one mention.
		self._standardize_coreferencing()


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


	def _read_sentence(self, sentence_tag):
		'''
		Convert sentence tags to python dictionaries.
		'''
		# Note that CoreNLP uses 1-based indexing for sentence ids.  We
		# convert to 0-based indexing.
		sentence =  Sentence({
			'id': int(sentence_tag['id']) - 1,
			'tokens': self._read_tokens(sentence_tag),
			'root': Token(),
			#'parse': self.read_parse(sentence_tag.find('parse').text),
		})

		# Give the tokens the dependency tree relation
		self._read_dependencies(sentence, sentence_tag)

		# Group the named entities together, and find the headword within
		sentence['entities'] = self._read_entities(sentence['tokens'])

		# Add tokens to global list and to the token offset-lookup table
		# Exclude the "null" tokens that simulate sentence head.
		self.tokens.extend(sentence['tokens'])

		token_offsets = dict([
			(t['character_offset_begin'], t) for t in sentence['tokens']
		])
		self.tokens_by_offset.update(token_offsets)

		return sentence


	def _read_dependencies(self, sentence, sentence_tag):

		if self.dependencies == 'collapsed-ccprocessed':
			dependencies_type = 'collapsed-ccprocessed-dependencies'
		elif self.dependencies == 'collapsed':
			dependencies_type = 'collapsed-dependencies'
		elif self.dependencies == 'basic':
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

			dependent_idx = int(dep.find('dependent')['idx']) - 1
			dependent = sentence['tokens'][dependent_idx]

			governor_idx = int(dep.find('governor')['idx']) - 1

			# When the governor idx is -1, it means that the dependent
			# token is the root of the sentence.  Simply mark it as such
			# and continue to the next dependency entry
			if governor_idx < 0:
				sentence['root'] = dependent
				dependent['parents'] = []
				continue

			# Otherwise there is a distinct governor token, and we'll
			# need to build the two-way link between governor and dependent
			else:
				governor = sentence['tokens'][governor_idx]

			# refuse to add a link which would create a cycle 
			if governor_idx in self.collect_descendents(dependent):
				continue

			dep_type = dep['type']
		
			governor['children'].append((dep_type, dependent))
			dependent['parents'].append((dep_type, governor))


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


	def _read_entities(self, tokens):
		'''
		collect the entities into a mention-like object
		'''

		entities = []
		last_entity_type = None
		cur_entity = None
		entity_idx = -1

		for token in tokens:

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

		# NOTE: head may be none
		return head


	def _read_tokens(self, sentence_tag):
		'''
		Convert token tag to python dictionary.
		'''

		# Note, in CoreNLP's xml, token ids and sentence ids are 1-based.
		# We convert to 0-based indices.
		sentence_id = int(sentence_tag['id']) - 1

		tokens = []
		for token_tag in sentence_tag.find_all('token'):

			# The "Speaker" property can be missing, so handle that case
			if token_tag.find('Speaker') is not None:
				speaker = token_tag.find('Speaker').text
			else:
				speaker = None

			# Get rest of the token's properties and make a Token object
			token = Token({
				'id': int(token_tag['id']) - 1,
				'sentence_id': sentence_id,
				'word': self.fix_word(token_tag.find('word').text),
				'lemma': token_tag.find('lemma').text,
				'pos': token_tag.find('pos').text,
				'ner': (
					None if token_tag.find('ner').text == 'O' 
					else token_tag.find('ner').text),
				'character_offset_begin': int(
					token_tag.find('characteroffsetbegin').text),
				'character_offset_end': int(
					token_tag.find('characteroffsetend').text),
				'speaker': speaker,
				'children': [],
				'parents': [],
				'mentions': []
			})

			tokens.append(token)

		return tokens

	def fix_word(self, word):
		if word == '-LRB-':
			return '('
		if word == '-RRB-':
			return ')'

		return word#.encode('utf8').decode('unicode-escape')


	def __str__(self):
		sentence_strings = []
		for i, s in enumerate(self.sentences):
			tokens = ' '.join([t['word'] for t in s['tokens']])
			sentence_string = 'Sentence %d:\n%s' % (i, tokens)
			sentence_strings.append(sentence_string)

		return '\n\n'.join(sentence_strings)

	
	def __repr__(self):
		return self.__str__()



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
		return ' '.join([t['word'] for t in self['tokens']])


	def __str__(self):

		string = 'Sentence %d:\n' % self['id']

		for t in self['tokens']:
			string += '\t%s\n' % str(t)

		return string


	def __repr__(self):
		return self.__str__()


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
			return '[no tokens!]'

		string = str(self['root']) + '\n'
		string += self._dep_tree_str(self['root'])
		return string


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

		offset = '(%d,%d)' % ( 
			self['character_offset_begin'], 
			self['character_offset_end']
		)
		ner = self['ner'] if self['ner'] is not None else '-'

		description = '%2d: %s %s %s %s' % (
			self['id'], self['word'], offset, self['pos'], ner
		)

		description = description.encode('utf8')

		return description


	def __repr__(self):
		return self.__str__()


	def get_parents(self):
		return self['parents'] if 'parents' in self else []


	def get_children(self):
		return self['children'] if 'children' in self else []


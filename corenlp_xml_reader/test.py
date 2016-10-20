import json
from os import path
from unittest import main, TestCase
from annotated_text import AnnotatedText as A

HERE = path.abspath(path.dirname(__file__))
AIDA_PATH = path.join(HERE, 'data/AIDA/b670037f5942445d.txt.json')
CORENLP_PATH = path.join(HERE, 'data/CoreNLP/b670037f5942445d.txt.xml')
UNICODE_AIDA_PATH = path.join(
	HERE, 'data/AIDA/b671489a0ff0e6c4.txt.json')
UNICODE_CORENLP_PATH = path.join(
	HERE, 'data/CoreNLP/b671489a0ff0e6c4.txt.xml')
DATA_DIR = path.join(path.dirname(__file__), 'data')


def load_test_article():
	return A(open(CORENLP_PATH).read(), open(AIDA_PATH).read())


def read_test_aida():
	return json.loads(open(AIDA_PATH).read())

def load_unicode_article():
	return A(
		open(UNICODE_CORENLP_PATH).read(),
		open(UNICODE_AIDA_PATH).read()
	)



class TestEntityLinking(TestCase):

	def test_find_best_mention_overlap(self):
		# Work out the path to the relevant testing article
		article_id = 'b67027bb45a91ee4.txt'
		aida_path = path.join(DATA_DIR, 'AIDA', article_id + '.json')
		core_path = path.join(DATA_DIR, 'CoreNLP', article_id + '.xml')

		# Load the article, as well as the AIDA object
		article = A(open(core_path).read(), open(aida_path).read())
		aida = json.loads(open(aida_path).read())

		# Get the relevant mention and its character range
		aida_mention = aida['mentions'][6]
		start = aida_mention['offset']
		end = start + aida_mention['length']

		# Get the competing candidate mentions from the AnnotatedText
		# instance that could be matched to `aida_mention`
		incorrect_core_mention = article.sentences[4]['mentions'][0]
		correct_core_mention = article.sentences[4]['mentions'][1]
		mentions = [incorrect_core_mention, correct_core_mention]

		# Ensure that the correct core mention is identified based on
		# it's character overlap with the aida mention
		retrieved = article._find_best_mention_overlap(mentions, start, end)

		self.assertEqual(retrieved, correct_core_mention)


	def test_entity_linking(self):
		# Work out the path to the relevant testing article
		article_id = 'b67027bb45a91ee4.txt'
		aida_path = path.join(DATA_DIR, 'AIDA', article_id + '.json')
		core_path = path.join(DATA_DIR, 'CoreNLP', article_id + '.xml')

		# Load the article, as well as the AIDA object
		article = A(open(core_path).read(), open(aida_path).read())
		aida = json.loads(open(aida_path).read())

		# Get the relevant mention for this test case
		aida_mention = aida['mentions'][6]

		# Get the competing candidate mentions from the AnnotatedText
		# instance that could be matched to `aida_mention`
		incorrect_core_mention = article.sentences[4]['mentions'][0]
		correct_core_mention = article.sentences[4]['mentions'][1]

		# Ensure that the correct core mention has the corresponding
		# knowldege base identifier from the aida mention
		self.assertEqual(
			correct_core_mention['kbIdentifier'], 
			aida_mention['bestEntity']['kbIdentifier']
		)

		# Ensure that the incorrect core mention has no kbIdentifier
		with self.assertRaises(KeyError):
			incorrect_core_mention['kbIdentifier'], 


class TestBasicLoad(TestCase):

	def test_basic_load(self):
		article = load_test_article()

	def test_print(self):
		article = load_test_article()
		expected = ' 0: President (0,9) NNP -'
		actual_str = str(article.sentences[0]['tokens'][0])
		actual_repr = repr(article.sentences[0]['tokens'][0])

		self.assertEqual(expected, actual_str)
		self.assertEqual(expected, actual_repr)


class TestUnicodeTokens(TestCase):

	def test_unicode_tokens(self):
		article = load_unicode_article()
		str(article.sentences[6])


if __name__ == '__main__':
	main()



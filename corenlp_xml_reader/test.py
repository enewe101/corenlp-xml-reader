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


def load_test_article():
	return A(open(CORENLP_PATH).read(), open(AIDA_PATH).read())


def read_test_aida():
	return json.loads(open(AIDA_PATH).read())

def load_unicode_article():
	return A(
		open(UNICODE_CORENLP_PATH).read(),
		open(UNICODE_AIDA_PATH).read()
	)


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



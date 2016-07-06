import json

from unittest import main, TestCase
from annotated_text import AnnotatedText as A

AIDA_PATH = '../data/AIDA/b670037f5942445d.txt.json'
CORENLP_PATH = '../data/CoreNLP/b670037f5942445d.txt.xml'


def load_test_article():
	return A(open(CORENLP_PATH).read(), open(AIDA_PATH).read())

def read_test_aida():
	return json.loads(open(AIDA_PATH).read())

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


if __name__ == '__main__':
	main()



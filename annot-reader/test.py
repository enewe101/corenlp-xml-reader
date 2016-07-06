from unittest import main, TestCase
from annotated_article import AnnotatedArticle as A

class TestBasicLoad(TestCase):

	AIDA_PATH = '../data/AIDA/b670037f5942445d.txt.json'
	CORENLP_PATH = '../data/CoreNLP/b670037f5942445d.txt.xml'

	def test_basic_load(self):
		article = A(
			open(self.CORENLP_PATH).read(),
			open(self.AIDA_PATH).read()
		)

	def test_print(self):
		article = A(
			open(self.CORENLP_PATH).read(),
			open(self.AIDA_PATH).read()
		)
		expected = 'Token 0: President (0,9) NNP -'
		actual_str = str(article.sentences[0]['tokens'][0])
		actual_repr = repr(article.sentences[0]['tokens'][0])

		self.assertEqual(expected, actual_str)
		self.assertEqual(expected, actual_repr)


if __name__ == '__main__':
	main()



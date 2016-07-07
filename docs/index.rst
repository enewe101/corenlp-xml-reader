.. corenlp-xml-reader documentation master file, created by
   sphinx-quickstart on Wed Jul  6 22:46:00 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Corenlp-xml-reader documentation
================================

Purpose
-------

Stanford's CoreNLP tool suite is a full-featured tool for generating 
annotations in text like POS (part-of-speech) tags and the dependency 
parse.

The CoreNLP tool can output the annotations to xml files.  
Working with these files is a bit tricky: it is up to the reading
program to rebuild the logical links between the various kinds of
information (e.g. POS, parse, and coreference information, etc).  

The format also has some questionable aspects.  It uses one-based indexing 
for sentence and token ids, while character offsets are zero-based.
Also, named entities and coreference chains don't have a consistent
relationship to one another.

The ``corenlp_xml_reader`` provides an API in Python that simplifies
access to CoreNLP's annotations and traversal of the document, while
ironing out some of the inconsistencies.

Install
-------

Basic install: ``pip install corenlp-xml-reader``

Hackable install: 

.. code-block:: bash

   git clone https://github.com/enewe101/corenlp-xml-reader.git
   cd corenlp-xml-reader
   python setup.py develop

Example
-------

Suppose we have the one-sentence document:

   *President Obama cannot run for a third term (but I think he wants to).*

Let's assume that it has been processed by CoreNLP, creating the output 
file ``obama.txt.xml``.  Let's import the module and get an ``AnnotatedText`` object.


.. code-block:: python

   >>> from corenlp_xml_reader import AnnotatedText as A
   >>> xml = open('obama.txt.xml').read()
   >>> annotated_text = A(xml)

Usually you'll access parts of the document using the ``sentences`` list.

.. code-block:: python

   >>> len(annotated_text.sentences)
   1
   >>> sentence = annotated_text.sentences[0]
   >>> sentence.keys()
   ['tokens', 'entities', 'references', 'mentions', 'root', 'id']


A ``Sentence`` is a special class that, for the most part, feels like a 
simple ``dict``.  
The ``tokens`` property is a list of the sentence's tokens:

.. code-block:: python

   >>> obama = sentence.tokens[1]
   >>> obama
   ' 0: Obama (10,14) NNP PERSON'
   >>> term = sentence.tokens[7]
   >>> term
   ' 7: term (39,42) NN -'

Tokens have properties corresponding to CoreNLP's annotations, plus some 
other stuff:

.. code-block:: python

   >>> obama.keys()
   ['word', 'character_offset_begin', 'character_offset_end', 'pos', 
   'lemma', 'sentence_id', 'entity_idx', 'speaker', 'mention', 'parents', 
   'ner', 'id']

"Obama" is the name of a person, so, if CoreNLP is working well, it should
pick that up.  Named entity information is found in the ``ner`` property:

.. code-block:: python

   >>> obama['ner']
   'PERSON'
   >>> term['ner'] is None
   True

Similarly we can check the part-of-speech:

.. code-block:: python

   >>> obama['pos']
   'NNP'
   >>> term['pos']
   'NN'

We can traverse the dependency tree using the ``parents`` and ``children``
properties.  In our example, "run" is the parent of "Obama" 
(because "Obama" is the subject (``nsubj``) of "run"):

.. code-block:: python

    >>> relation, parent = obama['parents'][0]
    >>> relation
    u'nsubj'
    >>> parent
    ' 3: run (23,25) -'

If you're processing dependency trees, you'll often want to start with
the head word (which is like the root of the sentence).  Sentences have a
special ``root`` property that stores the head word.  Usually it's a verb:

.. code-block:: python

   >>> sentence['root']
   ' 3: run (23,25) -'

A coreference chain is a series of references to the same entity.  In our 
example, "President Obama" and "he" are each *mentions* from the same
coreference chain.  We can access all the mentions of a coreference chain.

First, we can get the mention that "Obama" is part of:

.. code-block:: python

    >>> first_mention = obama['mention']
    >>> first_mention.tokens
    [' 0: President (0,8) -', ' 1: Obama (10,14) PERSON']

Then, from a given mention, we can access the chain, and all other mentions.
The coreference chain that includes "President Obama" should also include
"he":

.. code-block:: python

   >>> reference = first_mention['reference']
   >>> len(reference['mentions'])
   2
   >>> reference['mentions'][1]['tokens']
   ['12: he (57,58) -']

We can access all of the mentions or all of the coreference chains, for 
a given sentence, using its ``mentions`` and ``references`` properties. 

.. code-block:: python

    >>> len(sentence['mentions'])
    2
    >>> len(sentence['references'])
    1

One thing to note is that mentions and references aren't necessarily 
anchored to any named entity.  But they often are: in our example, we 
had "Obama".  To contrast, consider this sentence:

   *The police are yet to find any suspects.  They say they will continue 
   their search.*

Here, "The police", "they" (which occurs twice), and "their" are all 
part of one coreference chain, yet none is a named entity.

To access *only* mentions that are named entities, use the ``entities`` 
property of the sentence.

The document as a whole also provides global ``mentions``, ``references``,
and ``entities`` properties which can be iterated over directly.

.. :py:class: AnnotatedText(corenlp_xml=None, aida_json=None[, dependencies='collapsed-ccprocessed', exclude_ordinal_NERs=False, exclude_long_mentions=False, long_mention_threshold=5, exclude_non_ner_coreferences=False])

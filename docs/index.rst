.. corenlp-xml-reader documentation master file, created by
   sphinx-quickstart on Wed Jul  6 22:46:00 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Corenlp-xml-reader documentation
================================

.. py:module:: corenlp_xml_reader

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

   >>> obama = sentence['tokens'][1]
   >>> obama
   ' 0: Obama (10,14) NNP PERSON'
   >>> term = sentence['tokens'][7]
   >>> term
   ' 7: term (39,42) NN -'

Tokens have properties corresponding to CoreNLP's annotations, plus some 
other stuff:

.. code-block:: python

   >>> obama.keys()
   ['word', 'character_offset_begin', 'character_offset_end', 'pos', 
   'lemma', 'sentence_id', 'entity_idx', 'speaker', 'mentions', 'parents', 
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

    >>> first_mention = obama['mentions'][0]
    >>> first_mention['tokens']
    [' 0: President (0,8) -', ' 1: Obama (10,14) PERSON']

Note that a token can be part of multiple mentions.  For example, consider
the phrase "Obama's pyjamas".  If his pyjamas are mentioned multiple times,
then there will be a coreference chain made for it, as well as Obama
himself.  And in the phrase "Obama's pyjamas", the token "Obama" is both 
part of a mention corresponding to the 44th President of the United States,
and part of a mention corresponding to some garments for sleeping.

Once we have gotten ahold of a mention, we can access the coreference
chain that it belongs to, which is found in the mention's ``'reference'`` 
property.  Conversely, if we have accessed a coreference chain, we can
find all of its mentions by looking at its ``'mentions'`` property.

In our sentence "President Obama" and "he" are part of the same coreference
chain.  Starting from the mention containing the token "Obama", we can
acces the coreference chain starting, and then access the other mention
of Obama (the one consisting of the token "he"):

.. code-block:: python

   >>> reference = first_mention['reference']
   >>> len(reference['mentions'])
   2
   >>> second_mention = reference['mentions'][1]
   >>> second_mention['tokens']
   ['12: he (57,58) -']

Mentions have various properties:

.. code-block:: python

   >>> first_mention.keys()
   ['head', 'end', 'reference', 'tokens', 'start', 'sentence_id']

In addition to the coreference chain (``'reference'``), we get the id of 
the sentence in which the mention is found, the list
of token objects in the mention, the slice indices 
(``'start'`` and ``'end'``) for those tokens as they occur in the 
sentence's token list, and the head token of the 
mentinon.

References have various properties too:

.. code-block:: python

   >>> reference.keys()
   ['mentions', 'id', 'representative']

In addition to the mentions that are part of the coreference chain, we
get an id for the coreference chain (unique on a per-article-basis), 
and a reference to the
"representative" mention.  The representative mention is the one that is
deemed to have the fullest realization of the object's name.  So in our
example, the representative reference would be "President Obama", not "he".
This is useful for getting the human-readable name to represent the
coreference chain.

We can access all of the mentions or all of the coreference chains, for 
a given sentence, using its ``mentions`` and ``references`` properties. 

.. code-block:: python

    >>> len(sentence['mentions'])
    2
    >>> len(sentence['references'])
    1

One thing to note is that mentions and references aren't necessarily 
anchored to any named entity (though they often are). 
For example, consider this sentence:

   *The police are yet to find any suspects.  They say they will continue 
   their search.*

Here, "The police", "they" (which occurs twice), and "their" are all 
part of one coreference chain, yet none is a named entity.

To access *only* mentions that are named entities, use the ``entities`` 
property of the sentence.

The document as a whole also provides global ``mentions``, ``references``,
and ``entities`` properties which can be iterated over directly..

.. py:class:: AnnotatedText(corenlp_xml, **kwargs)

   Create a new AnnotatedText object.  Only the first parameter is normally
   needed.  The remaining parameters enable adding entity linking data from
   the AIDA software, controlling the kind of dependency parse
   used, and filtering the kinds of named entities, coreference chains,
   and mentions that are included (by default all those provided by CoreNLP
   are are included).

   :param str corenlp_xml: An xml string output by CoreNLP.
   :param str aida_json=None: A JSON string output by AIDA.  AIDA is a program that disambiguates named entities, linking them to the YAGO knowledge base.  If the JSON output of AIDA is provided, then ``entities``, ``mentions`` and ``references`` entries will be augmented with entity linking information.
   :param str dependencies='collapsed-ccprocessed': Determines which kind of dependencies will be used in constructing dependency trees.  Three options are available: ``'collapsed-ccprocessed'`` (the default), ``'collapsed'``, and ``'basic'``.
   :param bool exclude_ordinal_NERs=False: Whether to recognize ordinal named entities.  If ``True``, named entities of the following types will be ignored: ``'TIME'``, ``'DATE'``, ``'NUMBER'``, ``'DURATION'``, ``'PERCENT'``, ``'SET'``, ``'ORDINAL'``, and ``'MONEY'``.
   :param bool exclude_long_mentions=False: CoreNLP occaisionally includes mentions, as part of coreference chains, that are very long noun phrases.  These mentions can be surprising and are often not useful.  Setting this option to ``True`` causes any mentions longer that the value specified by ``long_mention_threshold`` to be discarded (default length is 5 tokens).
   :param int long_mention_threshold=5: Maximum number of tokens allowed in a coreference chain mention, above which the mention will be ignored if ``exclude_long_mentions`` is ``True``.
   :param bool exclude_non_ner_coreferences=False: In some cases, it is only desirable to consider those coreference chains that have at least one named entity as a mention.  Setting this option to ``True`` will exclude references and their mentions if the reference includes no named entities.


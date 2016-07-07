.. corenlp-xml-reader documentation master file, created by
   sphinx-quickstart on Wed Jul  6 22:46:00 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Corenlp-xml-reader documentation
================================

Contents:

.. toctree::
   :maxdepth: 2

   Purpose <purpose>
   Basic Usage <basic>


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

Purpose
=======

Stanford's CoreNLP tool suite is a full-featured tool for generating 
annotations in text that mark grammatical structure and semantics.
Some example annotations are, part-of-speech (POS) tags which indicating 
which tokens are verbs, nouns, etc, and dependency parsing which 
indicates such things as which noun is the subject of a verb.

The CoreNLP tool can output the annotations to xml files.  Unfortunately,
working with these files takes considerable work.  For exmple, linking 
the role that a token plays in a dependency parse, to its POS role, or
to the coreference chain that it belongs in, necessitates manual lookups
accross dispersed parts of the xml file.

The ``corenlp_xml_reader`` provides a simple API that represents an
annotated document.  The document provides access to its sentences and
tokens, whose annotations can be accessed as key-value pairs.

Example
=======

::

   from corenlp_xml_reader import AnnotatedText as A
   annotated_text = A(open('path/to/file.xml').read()

yo

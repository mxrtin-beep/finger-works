
"""Next-word/word-completion suggestions for the on-screen keyboard, backed
by a real bigram language model built from NLTK's Brown corpus -- rather
than a hand-typed "common words" list, which either has to be absurdly
large to cover real usage or (if kept short) can't tell you anything about
which word is actually likely to follow which.

The model has two pieces, both derived straight from the corpus:

- Unigram counts (word -> how often it appears in the corpus overall) --
  used to rank suggestions when there's no prior-word context to go on
  (the very first word of a sentence, or a prefix with no matching bigram
  continuation).
- Bigram counts (word -> Counter of {next_word: count}) -- used once a
  previous word is known, to answer "what's most likely to come right
  after this word". Repeatedly tapping the top suggestion is what lets
  this spell out a plausible (if simple) sentence one tap at a time, the
  same way a phone keyboard's predictive bar does -- a plain frequency
  list can't do that at all, since it never changes based on what came
  before.

Built once and cached to a pickle file next to this module -- the same
"download once, cache to disk" pattern main_fast.py already uses for the
hand-tracking model (see ensure_model_downloaded() there): the first run
downloads the ~3MB Brown corpus via NLTK if it isn't already present
(nltk caches corpora under ~/nltk_data, shared across projects), and every
run after that loads the small cached model file in a fraction of a
second instead of rescanning the whole corpus.
"""

import os
import pickle
import threading
from collections import Counter, defaultdict

import nltk

_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.word_model_cache.pkl')
_CORPUS_NAME = 'brown'

_unigram_counts = None   # Counter: word -> corpus-wide count
_bigram_counts = None    # dict: word -> Counter({next_word: count})
_ranked_words = None     # list of words, most common first (from _unigram_counts)
_lock = threading.Lock()

# Last-resort fallback ONLY -- used if the corpus can't be loaded at all
# (e.g. first run with no internet connection to download it, and no
# cached model file yet either), so the suggestion bar still shows
# *something* instead of going completely blank. Every other codepath
# uses the real corpus-backed model; this never provides next-word
# context, just enough to keep typing usable until the corpus is
# reachable.
_FALLBACK_WORDS = ['the', 'to', 'and', 'a', 'i', 'you', 'is', 'it', 'of', 'in']


def _load_from_cache():
	if not os.path.exists(_CACHE_PATH):
		return False
	try:
		with open(_CACHE_PATH, 'rb') as f:
			data = pickle.load(f)
		global _unigram_counts, _bigram_counts, _ranked_words
		_unigram_counts = data['unigrams']
		_bigram_counts = data['bigrams']
		_ranked_words = [word for word, _count in _unigram_counts.most_common()]
		return True
	except Exception as exc:
		print(f'[WARN] Could not load cached word-prediction model ({exc}); rebuilding from the corpus.')
		return False


def _build_from_corpus():
	global _unigram_counts, _bigram_counts, _ranked_words

	try:
		nltk.data.find(f'corpora/{_CORPUS_NAME}')
	except LookupError:
		print('Downloading NLTK Brown corpus for word predictions (one-time)...')
		nltk.download(_CORPUS_NAME, quiet=True)

	from nltk.corpus import brown

	unigrams = Counter()
	bigrams = defaultdict(Counter)
	prev_word = None
	for raw_word in brown.words():
		word = raw_word.lower()
		if not word.isalpha():
			# Punctuation/numbers aren't suggestable words themselves, and
			# they break the sentence's word chain -- the word after a
			# period isn't a real continuation of the word before it.
			prev_word = None
			continue
		unigrams[word] += 1
		if prev_word is not None:
			bigrams[prev_word][word] += 1
		prev_word = word

	_unigram_counts = unigrams
	_bigram_counts = dict(bigrams)
	_ranked_words = [word for word, _count in unigrams.most_common()]

	try:
		with open(_CACHE_PATH, 'wb') as f:
			pickle.dump({'unigrams': unigrams, 'bigrams': _bigram_counts}, f)
	except OSError as exc:
		print(f'[WARN] Could not cache word-prediction model to disk: {exc}')


def ensure_model_loaded():
	"""Load the cached model, or build it from the corpus (downloading the
	corpus first if needed) if there's no cache yet. Thread-safe and
	idempotent -- safe to call once from a background "preload" thread at
	startup (see main_fast.py, same idea as its camera-open/hand-model
	threads) so the first real keystroke doesn't have to wait on it, and
	safe to also call lazily from get_suggestions() in case that preload
	hasn't finished yet."""
	global _unigram_counts, _bigram_counts, _ranked_words
	if _unigram_counts is not None:
		return
	with _lock:
		if _unigram_counts is not None:
			return
		if _load_from_cache():
			return
		try:
			_build_from_corpus()
		except Exception as exc:
			print(
				f'[WARN] Could not build the word-prediction model ({exc}); '
				'falling back to a small built-in word list until the corpus is reachable.'
			)
			_unigram_counts = Counter(_FALLBACK_WORDS)
			_bigram_counts = {}
			_ranked_words = list(_FALLBACK_WORDS)


def get_suggestions(current_word, previous_word='', max_suggestions=3):
	"""Up to `max_suggestions` word suggestions.

	`current_word` is whatever's been typed of the word in progress so far
	(no spaces) -- non-empty means "complete this word": candidates are
	pulled first from `previous_word`'s bigram continuations that also
	match this prefix (so context still narrows things down even
	mid-word), then padded out with the corpus's overall most-common words
	starting with that prefix.

	`current_word` empty means the cursor is right after a space/newline
	(or at the very start) -- there's no partial word to complete, so
	these are pure *next*-word suggestions: `previous_word`'s most common
	bigram continuations, padded with the corpus's overall most-common
	words if `previous_word` has too few (or no) recorded continuations.
	Tapping the same (top) suggestion repeatedly walks this bigram chain
	one likely word at a time, which is what lets it spell out a
	plausible short sentence rather than looping on the same few words.
	"""
	ensure_model_loaded()

	prev_key = previous_word.lower() if previous_word else None
	bigram_continuations = _bigram_counts.get(prev_key) if prev_key else None

	if current_word:
		prefix = current_word.lower()
		candidates = []
		if bigram_continuations:
			for word, _count in bigram_continuations.most_common():
				if word.startswith(prefix):
					candidates.append(word)
				if len(candidates) >= max_suggestions:
					break
		if len(candidates) < max_suggestions:
			for word in _ranked_words:
				if len(candidates) >= max_suggestions:
					break
				if word.startswith(prefix) and word not in candidates:
					candidates.append(word)
		return candidates[:max_suggestions]

	candidates = [word for word, _count in bigram_continuations.most_common(max_suggestions)] if bigram_continuations else []
	if len(candidates) < max_suggestions:
		for word in _ranked_words:
			if len(candidates) >= max_suggestions:
				break
			if word not in candidates:
				candidates.append(word)
	return candidates[:max_suggestions]

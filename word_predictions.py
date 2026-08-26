
"""Next-word/word-completion suggestions for the on-screen keyboard, backed
by a real bigram language model built from NLTK's Brown corpus -- rather
than a hand-typed "common words" list, which either has to be absurdly
large to cover real usage or (if kept short) can't tell you anything about
which word is actually likely to follow which.

The model has two pieces, both derived straight from the corpus:

- Unigram counts (word -> how often it appears in the corpus overall) --
  the "just plain common" signal, used both to rank prefix matches that
  have no bigram context yet and to keep a specific-but-rare bigram
  continuation from crowding out an overwhelmingly common word (see
  _score() below).
- Bigram counts (word -> Counter of {next_word: count}) -- the "what
  actually follows this word" signal. Repeatedly tapping the top
  suggestion is what lets this spell out a plausible (if simple) sentence
  one tap at a time, the same way a phone keyboard's predictive bar does
  -- a plain frequency list can't do that at all, since it never changes
  based on what came before.

Suggestions blend both signals (see _score()) rather than using bigram
matches exclusively: a pure "most common word that's ever followed X"
ranking can surface an obscure-but-grammatical noun over a vastly more
common word that simply never happened to follow X in this particular
~1M-word corpus (e.g. "the idea"/"the image" outranking plain "is" when
completing "the i...", even though "is" is one of the most common words
in English overall) -- blending in overall frequency keeps the very
common short words competitive instead of getting shut out by a handful
of specific noun phrases.

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
import re
import threading
import time
from collections import Counter, defaultdict

import nltk

_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.word_model_cache.pkl')

# Two corpora, deliberately different in register, combined into one model:
# - 'brown': ~1M words of edited 1960s prose (news, fiction, editorials) --
#   broad general-English vocabulary and grammar, but formal enough that
#   contractions are comparatively rare in it.
# - 'nps_chat': ~45K words of actual informal online chat messages -- short,
#   colloquial, contraction-heavy, which is a much closer match to what
#   someone actually types on a keyboard than 1960s journalism is. Without
#   it, "isn't"/"don't"/etc. exist in the model but can still lose out to
#   more formal (if individually rarer-in-real-typing) words that happen to
#   be common in edited prose, e.g. "island"/"issue" outranking "isn't".
# Brown alone was the original model; nps_chat is blended in specifically
# to correct that -- see get_suggestions()'s docstring.
_CORPUS_NAMES = ['brown', 'nps_chat']

# Bumped whenever _build_from_corpus()'s output would change for the same
# corpus (tokenization/scoring changes, not just corpus updates) -- a stale
# cache built by older code is silently rebuilt instead of quietly serving
# outdated data forever.
_CACHE_VERSION = 4

_unigram_counts = None   # Counter: word -> corpus-wide count
_bigram_counts = None    # dict: word -> Counter({next_word: count})
_ranked_words = None     # list of words, most common first (from _unigram_counts)
_words_by_first_letter = None  # dict: first char -> that subset of _ranked_words, same order
_unigram_total = 0       # sum(_unigram_counts.values()) -- cached, used every score() call
_lock = threading.Lock()

# How much weight a specific bigram continuation gets versus the word's
# plain overall frequency when both are available (see _score()). 1.0
# would trust bigram counts alone (the old behavior -- prone to a rare
# specific continuation outranking a vastly more common word); 0.0 would
# ignore context entirely and always suggest by raw frequency. 0.6 leans
# toward "what usually follows this word" while still letting a very
# common word win out over a weak/rare bigram match.
_BIGRAM_WEIGHT = 0.6

# A "real word" for suggestion purposes: letters, optionally with a single
# internal apostrophe (contractions like "isn't"/"it's", possessives like
# "atlanta's"). NLTK's Brown corpus (unlike Penn-Treebank-style
# tokenization) already keeps contractions as one token rather than
# splitting them into e.g. "is" + "n't" -- but a plain str.isalpha() check
# still rejects them outright because of the apostrophe, which is what
# silently dropped every contraction from the vocabulary regardless of how
# common it actually is in the source text. This regex accepts them
# instead, while still rejecting pure punctuation tokens (``, '', etc.)
# and numbers.
_WORD_RE = re.compile(r"^[a-z]+(?:'[a-z]+)?$")

# Defensive only: kept in case a differently-tokenized corpus is ever
# swapped in that *does* split contraction suffixes off as their own
# token (Penn-Treebank-style corpora do this, e.g. "isn't" -> "is",
# "n't") -- re-glues such a suffix onto the word right before it instead
# of letting it get dropped as its own (apostrophe-only, so already
# _WORD_RE-rejected) token. A no-op against the Brown corpus, which
# doesn't tokenize this way in the first place.
_CONTRACTION_SUFFIXES = {"n't", "'s", "'re", "'ve", "'ll", "'d", "'m"}

# Last-resort fallback ONLY -- used if the corpus can't be loaded at all
# (e.g. first run with no internet connection to download it, and no
# cached model file yet either), so the suggestion bar still shows
# *something* instead of going completely blank. Every other codepath
# uses the real corpus-backed model; this never provides next-word
# context, just enough to keep typing usable until the corpus is
# reachable.
_FALLBACK_WORDS = ['the', 'to', 'and', 'a', 'i', 'you', 'is', 'it', 'of', 'in']


def _index_unigrams():
	"""(Re)build `_ranked_words`, `_words_by_first_letter`, and
	`_unigram_total` from `_unigram_counts` -- called once after
	`_unigram_counts` is set, wherever it's set (cache load, corpus build,
	or the last-resort fallback list), so all three always agree with it.

	`_words_by_first_letter` exists so get_suggestions() never has to
	choose between scanning the *entire* vocabulary for a prefix match (a
	real but unnecessary cost paid every keystroke, see main_fast.py) and
	capping how far into the frequency list it looks (which silently loses
	every word starting with a rare letter -- 'x'/'z'/etc. words tend to
	rank far outside any reasonably small cap, so a capped scan finds
	nothing for them at all). Bucketing by first letter first means every
	prefix only ever scans the words that could possibly match, however
	rare its starting letter is, without scanning the other 25 buckets."""
	global _ranked_words, _words_by_first_letter, _unigram_total
	_ranked_words = [word for word, _count in _unigram_counts.most_common()]
	_unigram_total = sum(_unigram_counts.values())
	_words_by_first_letter = defaultdict(list)
	for word in _ranked_words:
		_words_by_first_letter[word[0]].append(word)


def _load_from_cache():
	if not os.path.exists(_CACHE_PATH):
		return False
	try:
		with open(_CACHE_PATH, 'rb') as f:
			data = pickle.load(f)
		if data.get('version') != _CACHE_VERSION:
			return False  # stale format/scoring -- rebuild from the corpus
		global _unigram_counts, _bigram_counts
		_unigram_counts = data['unigrams']
		_bigram_counts = data['bigrams']
		_index_unigrams()
		return True
	except Exception as exc:
		print(f'[WARN] Could not load cached word-prediction model ({exc}); rebuilding from the corpus.')
		return False


def _iter_cleaned_sentence_words(raw_tokens):
	"""Lowercase `raw_tokens` (one corpus sentence), re-glue split-off
	contraction suffixes onto the word before them, and drop anything
	that's neither a real word nor a contraction suffix (punctuation,
	numbers) -- yielding just the words that word-prediction should ever
	be able to suggest."""
	words = []
	for raw in raw_tokens:
		token = raw.lower()
		if token in _CONTRACTION_SUFFIXES and words:
			words[-1] += token
			continue
		if _WORD_RE.match(token):
			words.append(token)
		# Anything else (punctuation, numbers) is dropped -- not treated as
		# a sentence break, since a comma/quote mid-sentence ("Hello,
		# world") shouldn't stop "hello" and "world" from being counted as
		# a real bigram pair.
	return words


# nps_chat is ~25x smaller than brown (45K vs ~1.1M words), so merging raw
# counts would barely move the combined ranking at all -- brown would still
# dominate every word's score almost entirely. Its per-occurrence weight is
# boosted so its colloquial, contraction-heavy vocabulary actually has a
# real say in the blend (see _CORPUS_NAMES above for why it's included at
# all) without letting its much smaller vocabulary swamp brown's broader
# coverage outright.
_CHAT_CORPUS_WEIGHT = 15


# How many sentences _accumulate_corpus() processes between explicit
# time.sleep(0) yields (see below) -- purely a scheduling nicety, doesn't
# change the model at all.
_YIELD_EVERY_N_SENTENCES = 500


def _accumulate_corpus(sentences, unigrams, bigrams, weight=1):
	for sentence_idx, raw_sentence in enumerate(sentences):
		words = _iter_cleaned_sentence_words(raw_sentence)
		for idx, word in enumerate(words):
			unigrams[word] += weight
			if idx > 0:
				bigrams[words[idx - 1]][word] += weight
		if sentence_idx % _YIELD_EVERY_N_SENTENCES == 0:
			# This only ever runs on the background "preload" thread (see
			# ensure_model_loaded()/main_fast.py), built once and then
			# cached to disk -- but that one-time build is a solid second
			# or two of tight, pure-Python looping over ~1.2M words, which
			# is exactly the kind of CPU-bound stretch that can crowd out
			# the main thread's camera/hand-tracking/click-detection work
			# under the GIL if it runs as one uninterrupted burst.
			# time.sleep(0) forces a context switch without actually
			# delaying the build in any meaningful way (a couple thousand
			# extra yields adds negligible wall-clock time), spreading the
			# CPU cost out in small pieces instead of hogging the
			# interpreter for seconds at a stretch.
			time.sleep(0)


def _build_from_corpus():
	global _unigram_counts, _bigram_counts

	for corpus_name in _CORPUS_NAMES:
		try:
			nltk.data.find(f'corpora/{corpus_name}')
		except LookupError:
			print(f'Downloading NLTK {corpus_name} corpus for word predictions (one-time)...')
			nltk.download(corpus_name, quiet=True)

	from nltk.corpus import brown, nps_chat

	unigrams = Counter()
	bigrams = defaultdict(Counter)
	_accumulate_corpus(brown.sents(), unigrams, bigrams)
	_accumulate_corpus(nps_chat.posts(), unigrams, bigrams, weight=_CHAT_CORPUS_WEIGHT)

	_unigram_counts = unigrams
	_bigram_counts = dict(bigrams)
	_index_unigrams()

	try:
		with open(_CACHE_PATH, 'wb') as f:
			pickle.dump({'version': _CACHE_VERSION, 'unigrams': unigrams, 'bigrams': _bigram_counts}, f)
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
	global _unigram_counts, _bigram_counts
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
			_index_unigrams()


def _score(word, bigram_continuations, bigram_total):
	"""How good a suggestion `word` is, blending "how often this specific
	word followed the previous one" with "how common this word is overall"
	(see the module docstring for why both matter -- a rare-but-valid
	bigram match otherwise crowds out a much more common word that just
	didn't happen to follow this exact previous word in the corpus).

	Both components are probabilities (0-1), so they're comparable
	regardless of the corpus's raw counts: bigram_prob is "of all the
	words that followed the previous word, what fraction were this one",
	unigram_prob is "of all words in the corpus, what fraction were this
	one". `_BIGRAM_WEIGHT` controls the blend between them.
	"""
	bigram_prob = (
		bigram_continuations[word] / bigram_total
		if bigram_continuations and bigram_total and word in bigram_continuations
		else 0.0
	)
	unigram_prob = (_unigram_counts.get(word, 0) / _unigram_total) if _unigram_total else 0.0
	return _BIGRAM_WEIGHT * bigram_prob + (1 - _BIGRAM_WEIGHT) * unigram_prob


# Cap on how many of a previous word's bigram continuations are ever
# considered -- the top 50 already comfortably cover every continuation
# with any real chance of matching a short prefix; a rare word's full
# continuation list can otherwise run into the hundreds for no benefit.
# There's no equivalent cap on the *unigram* side any more -- see
# _words_by_first_letter above for why an arbitrary cap there was actively
# wrong (it silently lost every rare-starting-letter word), not just slow.
_MAX_BIGRAM_CANDIDATES = 50


def get_suggestions(current_word, previous_word='', max_suggestions=3):
	"""Up to `max_suggestions` word suggestions.

	`current_word` is whatever's been typed of the word in progress so far
	(no spaces). Non-empty means "complete this word": only words starting
	with it are considered, ranked by the blended _score() above (bigram
	continuation of `previous_word` plus overall frequency) -- blending in
	overall frequency here is what keeps a very common short word (e.g.
	"is") competitive against a handful of rarer-but-valid bigram matches
	(e.g. "idea"/"image" after "the") that would otherwise crowd out
	everything else just for having a specific, if rare, precedent in the
	corpus.

	`current_word` empty (right after a space/newline, or at the very
	start) means there's no partial word to complete -- these are pure
	*next*-word suggestions, and deliberately NOT blended with overall
	frequency the way completions are: blending would let hyper-common
	words (the/of/and/...) win almost every time purely on raw frequency,
	regardless of whether they're a sensible continuation of
	`previous_word` at all (a first version of this did exactly that, and
	degenerated into suggesting "the" forever). Instead this uses
	`previous_word`'s bigram continuations first (most common first),
	only padding with the corpus's overall most-common words if there
	are too few (or no) recorded continuations to fill `max_suggestions`.
	Tapping the same (top) suggestion repeatedly walks the resulting
	bigram chain one likely word at a time, which is what lets this spell
	out a plausible short sentence rather than looping on the same word.
	"""
	ensure_model_loaded()

	prev_key = previous_word.lower() if previous_word else None
	bigram_continuations = _bigram_counts.get(prev_key) if prev_key else None

	if current_word:
		prefix = current_word.lower()
		bigram_total = sum(bigram_continuations.values()) if bigram_continuations else 0

		candidates = set()
		if bigram_continuations:
			for word, _count in bigram_continuations.most_common(_MAX_BIGRAM_CANDIDATES):
				if word.startswith(prefix):
					candidates.add(word)
		for word in _words_by_first_letter.get(prefix[0], []):
			if word.startswith(prefix):
				candidates.add(word)

		ranked = sorted(candidates, key=lambda w: _score(w, bigram_continuations, bigram_total), reverse=True)
		return ranked[:max_suggestions]

	candidates = []
	if bigram_continuations:
		for word, _count in bigram_continuations.most_common():
			if word != prev_key:  # guard against a stray "the the"-style self-repeat in the counts
				candidates.append(word)
			if len(candidates) >= max_suggestions:
				break
	if len(candidates) < max_suggestions:
		for word in _ranked_words:
			if len(candidates) >= max_suggestions:
				break
			if word != prev_key and word not in candidates:
				candidates.append(word)
	return candidates[:max_suggestions]

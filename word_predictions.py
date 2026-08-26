
"""Next-word/word-completion suggestions for the on-screen keyboard.

Mirrors the "three word suggestions above the keys" strip iPhones show while
typing: given the letters typed so far for the current word, offer up to
three likely completions to tap instead of finishing the word by hand. Once
a word is finished (a space was just typed, or nothing's been typed yet),
offer three likely *next* words instead -- based on the word that was just
finished, when it's one of a curated set of common lead-ins (see
_NEXT_WORD_MAP below), falling back to three common words otherwise, same
as a fresh phone keyboard offers before you've typed anything at all.

Deliberately simple -- static frequency-ordered word lists plus a prefix
match and a small hand-picked word -> likely-next-words table -- rather
than a real language model. That's enough to give the same "tap instead of
typing the rest, and the suggestions actually change as you type" feel
without pulling in a model file, a training corpus, or a dependency this
project doesn't otherwise need.
"""

# Ordered roughly by how common each word is in everyday English (most
# frequent first) -- suggestions are picked by walking this list in order
# and taking the first matches, so more common words are preferred over
# rarer ones that happen to share the same prefix.
#
# This covers a lot more ground than just the top handful of words
# specifically so that typing almost any single letter still turns up at
# least one real suggestion instead of the bar going empty -- a short list
# only really covering "th"/"a"/"the" reads as broken the moment you type a
# less common starting letter.
COMMON_WORDS = [
	'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
	'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
	'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she',
	'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their', 'what',
	'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go', 'me',
	'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know', 'take',
	'people', 'into', 'year', 'your', 'good', 'some', 'could', 'them', 'see', 'other',
	'than', 'then', 'now', 'look', 'only', 'come', 'its', 'over', 'think', 'also',
	'back', 'after', 'use', 'two', 'how', 'our', 'work', 'first', 'well', 'way',
	'even', 'new', 'want', 'because', 'any', 'these', 'give', 'day', 'most', 'us',
	'is', 'was', 'are', 'been', 'has', 'had', 'were', 'said', 'did', 'having',
	'may', 'am', 'here', 'need', 'thanks', 'thank', 'please', 'sorry', 'yes', 'okay',
	'hello', 'hi', 'love', 'great', 'really', 'very', 'much', 'more', 'still', 'again',
	'right', 'today', 'tomorrow', 'yesterday', 'never', 'always', 'sure', 'maybe', 'why', 'where',
	'going', 'let', 'sure', 'talk', 'call', 'meet', 'meeting', 'later', 'soon', 'week',
	'work', 'home', 'school', 'help', 'need', 'find', 'ask', 'tell', 'feel', 'seem',
	'leave', 'put', 'mean', 'keep', 'let', 'begin', 'start', 'show', 'hear', 'play',
	'run', 'move', 'live', 'believe', 'bring', 'happen', 'write', 'sit', 'stand', 'lose',
	'pay', 'meet', 'include', 'continue', 'set', 'learn', 'change', 'lead', 'understand', 'watch',
	'follow', 'stop', 'create', 'speak', 'read', 'allow', 'add', 'spend', 'grow', 'open',
	'walk', 'win', 'offer', 'remember', 'love', 'consider', 'appear', 'buy', 'wait', 'serve',
	'die', 'send', 'expect', 'build', 'stay', 'fall', 'cut', 'reach', 'kill', 'remain',
	'best', 'better', 'same', 'old', 'big', 'small', 'large', 'long', 'little', 'own',
	'different', 'high', 'low', 'next', 'early', 'young', 'important', 'few', 'public', 'able',
	'yeah', 'nope', 'yep', 'awesome', 'cool', 'nice', 'fine', 'ready', 'happy', 'sad',
	'sorry', 'excited', 'tired', 'busy', 'hungry', 'done', 'here', 'there', 'everyone', 'everything',
	'anything', 'something', 'nothing', 'someone', 'anyone', 'quick', 'quickly', 'actually', 'basically', 'probably',
	'definitely', 'exactly', 'totally', 'literally', 'honestly', 'obviously', 'seriously', 'currently', 'recently', 'usually',
	'jump', 'job', 'joke', 'join', 'just', 'kind', 'keep', 'key', 'kid', 'knew',
	'quite', 'quiet', 'question', 'quick', 'zero', 'zone', 'xerox', 'x-ray', 'value', 'various',
	'visit', 'view', 'voice', 'vote', 'very',
]

# Words that were just finished (the word before the cursor, once a space
# follows it) mapped to their most likely next words, most likely first --
# a small, hand-picked "bigram" table covering common sentence starters/
# connectors, just enough to make the empty-prefix suggestions actually
# change based on context (like a phone keyboard does) instead of always
# showing the same static three words after every completed word.
#
# Deliberately partial: only the lead-in words common enough to be worth
# hardcoding are here. Anything not in this table falls back to the plain
# COMMON_WORDS list in get_suggestions() below, same as it always did.
_NEXT_WORD_MAP = {
	'i': ['am', 'think', 'love'],
	"i'm": ['not', 'going', 'sorry'],
	'you': ['are', 'can', 'know'],
	"you're": ['welcome', 'right', 'not'],
	'thank': ['you'],
	'thanks': ['for', 'a', 'so'],
	'how': ['are', 'much', 'do'],
	'what': ['is', 'do', 'about'],
	'is': ['it', 'this', 'that'],
	'are': ['you', 'we', 'there'],
	'do': ['you', 'not', 'we'],
	'can': ['you', 'we', 'i'],
	'will': ['be', 'you', 'not'],
	'let': ['me', 'us', 'me know'],
	'the': ['same', 'best', 'first'],
	'a': ['lot', 'few', 'little'],
	'to': ['be', 'the', 'do'],
	'and': ['i', 'the', 'then'],
	'it': ['is', 'was', "'s"],
	'that': ['is', 'was', 'would'],
	'this': ['is', 'was', 'will'],
	'have': ['a', 'to', 'been'],
	'good': ['morning', 'to', 'luck'],
	'see': ['you', 'if', 'you soon'],
	'talk': ['to', 'soon', 'later'],
	'sounds': ['good', 'great', 'like'],
	'looking': ['forward', 'for', 'at'],
	'sorry': ['for', 'about', 'i'],
	'please': ['let', 'send', 'do'],
	'of': ['the', 'course', 'a'],
	'in': ['the', 'a', 'order'],
	'on': ['the', 'it', 'my'],
	'for': ['the', 'you', 'a'],
	'with': ['the', 'you', 'a'],
}


def get_suggestions(current_word, previous_word='', max_suggestions=3):
	"""Up to `max_suggestions` word suggestions.

	`current_word` is whatever's been typed of the word in progress so far
	(no spaces) -- non-empty means "complete this word", and suggestions
	are a plain case-insensitive prefix match against COMMON_WORDS, walked
	in frequency order (so "th" offers "the"/"that"/"they" in that order,
	rather than every word that happens to contain "th" somewhere).

	`current_word` empty means the cursor is right after a space/newline
	(or at the very start) -- there's no partial word to complete, so these
	are *next*-word suggestions instead: `previous_word` (the word just
	finished, if any) is looked up in _NEXT_WORD_MAP for likely
	continuations; anything it doesn't cover, or an empty `previous_word`,
	falls back to the plain most-common-words list, same as a fresh phone
	keyboard shows before you've typed anything at all.
	"""
	if current_word:
		prefix = current_word.lower()
		matches = [word for word in COMMON_WORDS if word.startswith(prefix)]
		return matches[:max_suggestions]

	suggestions = list(_NEXT_WORD_MAP.get(previous_word.lower(), [])) if previous_word else []
	for word in COMMON_WORDS:
		if len(suggestions) >= max_suggestions:
			break
		if word not in suggestions:
			suggestions.append(word)
	return suggestions[:max_suggestions]

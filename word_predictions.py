
"""Next-word/word-completion suggestions for the on-screen keyboard.

Mirrors the "three word suggestions above the keys" strip iPhones show while
typing: given the letters typed so far for the current word, offer up to
three likely completions to tap instead of finishing the word by hand; with
nothing typed yet, offer three common words to kick off a sentence with one
tap instead.

Deliberately simple -- a static frequency-ordered word list plus a prefix
match -- rather than a real language model. That's enough to give the same
"tap instead of typing the rest" experience without pulling in a model file,
a training corpus, or a dependency this project doesn't otherwise need.
"""

# Ordered roughly by how common each word is in everyday English (most
# frequent first) -- suggestions are picked by walking this list in order
# and taking the first matches, so more common words are preferred over
# rarer ones that happen to share the same prefix.
#
# This is a small, hand-picked list (a few hundred of the most common
# English words) rather than an exhaustive dictionary -- plenty for
# realistic short-word/short-sentence suggestions, without needing to ship
# or load a large wordlist file.
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
]


def get_suggestions(current_word, max_suggestions=3):
	"""Up to `max_suggestions` word suggestions for `current_word`.

	`current_word` is whatever's been typed of the current word so far (no
	spaces) -- an empty string means the user hasn't typed anything for this
	word yet (either at the very start, or right after a space), in which
	case the three most common words overall are offered, same as an
	iPhone's suggestion bar on an empty text field.

	Matching is a plain case-insensitive prefix match against COMMON_WORDS,
	walked in frequency order -- so "th" offers "the"/"that"/"they" (in that
	order) rather than every word that happens to contain "th" somewhere, or
	an alphabetical-but-rarer match ahead of a more common one.
	"""
	if not current_word:
		return COMMON_WORDS[:max_suggestions]

	prefix = current_word.lower()
	matches = [word for word in COMMON_WORDS if word.startswith(prefix)]
	return matches[:max_suggestions]

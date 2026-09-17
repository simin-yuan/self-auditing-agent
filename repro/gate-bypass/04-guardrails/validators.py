"""Custom guardrails-ai validators for the support-agent output guard.

rail.xml references these rules by name; guardrails-ai resolves each name
through the registry that @register_validator fills in.  Delete a rule from
rail.xml and the corresponding class here simply stops being called.
"""
import re

from guardrails import register_validator
from guardrails.validator_base import FailResult, PassResult, Validator

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?\d{1,3}[ -]?)?(?:\(\d{3}\)|\b\d{3})[ -]?\d{3}[ -]?\d{4}\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
URL = re.compile(r"https?://\S+|www\.\S+")
COMPETITORS = ("acme-corp", "globex", "initech")
PROFANITY = ("damn", "crap", "idiot")


@register_validator(name="no-pii", data_type="string")
class NoPII(Validator):
    """Reject output carrying personal or payment data."""

    def validate(self, value, metadata):
        for rx, kind in ((EMAIL, "email"), (PHONE, "phone"), (CARD, "card")):
            hit = rx.search(value)
            if hit:
                return FailResult(
                    error_message="PII (%s) leaked in output: %r" % (kind, hit.group(0))
                )
        return PassResult()


@register_validator(name="no-competitor-mention", data_type="string")
class NoCompetitorMention(Validator):
    """Reject output naming a competitor product."""

    def validate(self, value, metadata):
        low = value.lower()
        for name in COMPETITORS:
            if name in low:
                return FailResult(error_message="competitor named: %s" % name)
        return PassResult()


@register_validator(name="no-url", data_type="string")
class NoUrl(Validator):
    """Reject output containing a link (answers must stay link-free)."""

    def validate(self, value, metadata):
        hit = URL.search(value)
        if hit:
            return FailResult(error_message="link in output: %r" % hit.group(0))
        return PassResult()


@register_validator(name="no-profanity", data_type="string")
class NoProfanity(Validator):
    """Reject output containing a blocked term."""

    def validate(self, value, metadata):
        low = value.lower()
        for word in PROFANITY:
            if word in low:
                return FailResult(error_message="blocked term in output: %s" % word)
        return PassResult()


@register_validator(name="max-words", data_type="string")
class MaxWords(Validator):
    """Reject output longer than the configured word budget."""

    def __init__(self, limit, **kwargs):
        self.limit = int(limit)
        super().__init__(**kwargs)

    def validate(self, value, metadata):
        n = len(value.split())
        if n > self.limit:
            return FailResult(error_message="output is %d words (limit %d)" % (n, self.limit))
        return PassResult()

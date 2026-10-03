"""
Rate limiting / throttling for credential verification endpoints per Phase 9 and Phase 14 spec.
Prevents automated brute-force enumeration attacks on public credential IDs.
"""

from rest_framework.throttling import SimpleRateThrottle


class VerificationRateThrottle(SimpleRateThrottle):
    """
    Throttles verification requests by client IP address.
    Configured via REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['verification'].
    """
    scope = 'verification'

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident,
        }

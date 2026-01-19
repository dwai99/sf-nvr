"""
Compatibility fixes for Python 3.9
"""

import datetime
import sys

# Fix for datetime.UTC not available in Python < 3.11
if sys.version_info < (3, 11):
    if not hasattr(datetime, 'UTC'):
        datetime.UTC = datetime.timezone.utc

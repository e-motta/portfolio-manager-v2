#!/bin/bash
# Unit tests for remote-deploy.sh validation functions
#
# Run with: ./scripts/test-remote-deploy.sh

set -uo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

pass() {
    ((TESTS_PASSED++))
    echo -e "${GREEN}PASS${NC}: $1"
}

fail() {
    ((TESTS_FAILED++))
    echo -e "${RED}FAIL${NC}: $1"
}

run_test() {
    ((TESTS_RUN++))
}

# Extract validate_tag function for testing
# We can't source the whole script because it calls main() at the end
validate_tag() {
    local tag="$1"
    if [[ ! "$tag" =~ ^sha-[0-9a-f]{7,40}$ ]]; then
        return 1
    fi
    return 0
}

echo "Testing validate_tag..."
echo "======================"

# Valid tags
run_test
if validate_tag "sha-abc1234"; then
    pass "sha-abc1234 (7 chars)"
else
    fail "sha-abc1234 should be valid"
fi

run_test
if validate_tag "sha-0123456789abcdef0123456789abcdef01234567"; then
    pass "sha-<40 hex chars> (full SHA)"
else
    fail "40-char SHA should be valid"
fi

run_test
if validate_tag "sha-deadbeef"; then
    pass "sha-deadbeef (8 chars)"
else
    fail "sha-deadbeef should be valid"
fi

run_test
if validate_tag "sha-0000000"; then
    pass "sha-0000000 (all zeros)"
else
    fail "sha-0000000 should be valid"
fi

run_test
if validate_tag "sha-fffffff"; then
    pass "sha-fffffff (all f's)"
else
    fail "sha-fffffff should be valid"
fi

# Invalid tags
run_test
if ! validate_tag "latest"; then
    pass "latest rejected"
else
    fail "latest should be rejected"
fi

run_test
if ! validate_tag "sha-"; then
    pass "sha- (empty) rejected"
else
    fail "sha- should be rejected"
fi

run_test
if ! validate_tag "sha-abc123"; then
    pass "sha-abc123 (6 chars) rejected"
else
    fail "sha-abc123 should be rejected (too short)"
fi

run_test
if ! validate_tag "sha-ABCDEFG"; then
    pass "sha-ABCDEFG (uppercase) rejected"
else
    fail "sha-ABCDEFG should be rejected (uppercase)"
fi

run_test
if ! validate_tag "sha-abc123g"; then
    pass "sha-abc123g (invalid hex) rejected"
else
    fail "sha-abc123g should be rejected (g is not hex)"
fi

run_test
if ! validate_tag ""; then
    pass "empty string rejected"
else
    fail "empty string should be rejected"
fi

run_test
if ! validate_tag "main"; then
    pass "main rejected"
else
    fail "main should be rejected"
fi

run_test
if ! validate_tag "sha-abc1234; rm -rf /"; then
    pass "command injection rejected"
else
    fail "command injection should be rejected"
fi

run_test
if ! validate_tag "sha-abc1234\nsha-def5678"; then
    pass "newline injection rejected"
else
    fail "newline injection should be rejected"
fi

# Note: null bytes truncate bash strings, so sha-abc1234\x00extra becomes sha-abc1234
# This is safe behavior - the injected content is discarded
run_test
if validate_tag $'sha-abc1234\x00extra'; then
    pass "null byte truncates to valid tag (safe)"
else
    fail "null byte truncation should leave valid tag"
fi

run_test
if ! validate_tag "SHA-abc1234"; then
    pass "SHA- (uppercase prefix) rejected"
else
    fail "SHA-abc1234 should be rejected (uppercase SHA)"
fi

# Edge case: 41 chars (too long)
run_test
if ! validate_tag "sha-0123456789abcdef0123456789abcdef012345678"; then
    pass "sha-<41 chars> rejected"
else
    fail "41-char SHA should be rejected (too long)"
fi

echo ""
echo "======================"
echo "Results: $TESTS_PASSED/$TESTS_RUN passed"

if [[ $TESTS_FAILED -gt 0 ]]; then
    echo -e "${RED}$TESTS_FAILED tests failed${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed${NC}"
    exit 0
fi

import re


def normalize(s: str) -> str:
    if s is None:
        return ''
    s = s.upper()
    s = re.sub(r'[\s\-\.]', '', s)
    s = s.replace('O', '0').replace('I', '1')
    return s


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) == 0:
        return len(b)
    if len(b) == 0:
        return len(a)
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        prev = dp[0]
        dp[0] = i
        for j, cb in enumerate(b, start=1):
            tmp = dp[j]
            cost = 0 if ca == cb else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = tmp
    return dp[-1]


def is_match(plate_target: str, ocr_text: str, mode: str = 'relaxed', max_distance: int = 2) -> bool:
    a = normalize(plate_target)
    b = normalize(ocr_text)
    if mode == 'exact':
        return a == b
    return levenshtein(a, b) <= max_distance



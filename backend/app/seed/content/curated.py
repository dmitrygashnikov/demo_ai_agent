"""Curated demo content base: theory, video reviews, and coding tasks.

Each TASK carries: prompt, entry_point, visible+hidden tests, a reference
solution (which is itself sandbox-verified before being shown), difficulty,
skill/concept, language, and (for real-world cases) a type tag.

This small base is enough to demonstrate the full end-to-end adaptive loop for
the ``loops`` concept in both Python and JavaScript, plus a couple of adjacent
concepts.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# THEORY documents (markdown). metadata: language, concept, type, level
# ---------------------------------------------------------------------------
THEORY = [
    {
        "language": "python",
        "concept": "loops",
        "level": "beginner",
        "title": "Python loops: range and off-by-one",
        "text": (
            "In Python, `for i in range(n)` iterates i = 0, 1, ..., n-1. "
            "A classic off-by-one bug is using range(1, n) when you need all n "
            "elements, or range(n+1) when you overshoot. To sum numbers 1..n use "
            "range(1, n+1). Remember: range(start, stop) excludes stop."
        ),
    },
    {
        "language": "python",
        "concept": "conditions",
        "level": "beginner",
        "title": "Python conditions",
        "text": (
            "Use if/elif/else for branching. Comparison operators: ==, !=, <, >, "
            "<=, >=. Combine with and/or/not. Indentation defines the block."
        ),
    },
    {
        "language": "javascript",
        "concept": "loops",
        "level": "beginner",
        "title": "JavaScript loops: for and off-by-one",
        "text": (
            "In JS, `for (let i = 0; i < n; i++)` runs i = 0..n-1. Using i <= n is "
            "the classic off-by-one overshoot. To sum 1..n: for (let i = 1; i <= n; "
            "i++) total += i. Array indices go 0..arr.length-1."
        ),
    },
]

# ---------------------------------------------------------------------------
# VIDEO reviews. metadata: language, concept, error_type, url, timecodes
# ---------------------------------------------------------------------------
VIDEOS = [
    {
        "language": "python",
        "concept": "loops",
        "error_type": "off_by_one",
        "title": "Off-by-one errors in Python loops explained",
        "url": "https://example.com/videos/py-loops-offbyone",
        "timecode": "00:00 intro, 02:30 range pitfalls, 05:10 fixing the bug",
        "text": (
            "Video walkthrough: why range(1, n) misses the last element and how "
            "range(1, n+1) fixes summation. Covers boundary reasoning step by step."
        ),
    },
    {
        "language": "python",
        "concept": "loops",
        "error_type": "logic",
        "title": "Loop logic and accumulators in Python",
        "url": "https://example.com/videos/py-loops-logic",
        "timecode": "00:00 accumulator pattern, 03:00 common mistakes",
        "text": "Explains the accumulator pattern (total += x) and resetting state.",
    },
    {
        "language": "javascript",
        "concept": "loops",
        "error_type": "off_by_one",
        "title": "JS off-by-one in for loops",
        "url": "https://example.com/videos/js-loops-offbyone",
        "timecode": "00:00 intro, 01:45 i<=n vs i<n",
        "text": "Why i <= n overshoots arrays and how to reason about bounds in JS.",
    },
]

# ---------------------------------------------------------------------------
# TASKS. metadata-rich; reference_solution is verified in sandbox before serve.
# kind: "practice" | "similar" | "real_case"
# ---------------------------------------------------------------------------
TASKS = [
    # ---- Python loops ----
    {
        "id": "py_loops_sum_1_n",
        "language": "python",
        "concept": "loops",
        "skill_id": "py_loops",
        "difficulty": 2,
        "kind": "practice",
        "entry_point": "sum_to_n",
        "prompt": "Write a function sum_to_n(n) that returns the sum of integers from 1 to n inclusive.",
        "reference_solution": "def sum_to_n(n):\n    total = 0\n    for i in range(1, n + 1):\n        total += i\n    return total\n",
        "visible_tests": [{"args": [5], "expected": 15}, {"args": [1], "expected": 1}],
        "hidden_tests": [{"args": [10], "expected": 55}, {"args": [100], "expected": 5050}],
    },
    {
        "id": "py_loops_count_even",
        "language": "python",
        "concept": "loops",
        "skill_id": "py_loops",
        "difficulty": 2,
        "kind": "similar",
        "entry_point": "count_even",
        "prompt": "Write count_even(nums) that returns how many numbers in the list nums are even.",
        "reference_solution": "def count_even(nums):\n    c = 0\n    for x in nums:\n        if x % 2 == 0:\n            c += 1\n    return c\n",
        "visible_tests": [{"args": [[1, 2, 3, 4]], "expected": 2}],
        "hidden_tests": [{"args": [[2, 4, 6]], "expected": 3}, {"args": [[1, 3, 5]], "expected": 0}],
    },
    {
        "id": "py_loops_factorial",
        "language": "python",
        "concept": "loops",
        "skill_id": "py_loops",
        "difficulty": 3,
        "kind": "similar",
        "entry_point": "factorial",
        "prompt": "Write factorial(n) returning n! using a loop. factorial(0) == 1.",
        "reference_solution": "def factorial(n):\n    r = 1\n    for i in range(2, n + 1):\n        r *= i\n    return r\n",
        "visible_tests": [{"args": [5], "expected": 120}],
        "hidden_tests": [{"args": [0], "expected": 1}, {"args": [6], "expected": 720}],
    },
    {
        "id": "py_loops_real_case_cleanup",
        "language": "python",
        "concept": "loops",
        "skill_id": "py_loops",
        "difficulty": 4,
        "kind": "real_case",
        "entry_point": "normalize_prices",
        "prompt": (
            "Real project case: a data pipeline receives a list of price strings like "
            "['$1.50', '$2.00']. Write normalize_prices(prices) returning a list of "
            "floats rounded to 2 decimals, skipping any entries that are not valid prices."
        ),
        "reference_solution": (
            "def normalize_prices(prices):\n"
            "    out = []\n"
            "    for p in prices:\n"
            "        try:\n"
            "            out.append(round(float(str(p).replace('$', '')), 2))\n"
            "        except ValueError:\n"
            "            continue\n"
            "    return out\n"
        ),
        "visible_tests": [{"args": [["$1.50", "$2.00"]], "expected": [1.5, 2.0]}],
        "hidden_tests": [{"args": [["$3", "bad", "$4.999"]], "expected": [3.0, 5.0]}],
    },
    # ---- Python conditions ----
    {
        "id": "py_cond_max2",
        "language": "python",
        "concept": "conditions",
        "skill_id": "py_conditions",
        "difficulty": 1,
        "kind": "practice",
        "entry_point": "max2",
        "prompt": "Write max2(a, b) returning the larger of two numbers.",
        "reference_solution": "def max2(a, b):\n    return a if a > b else b\n",
        "visible_tests": [{"args": [3, 7], "expected": 7}],
        "hidden_tests": [{"args": [9, 2], "expected": 9}, {"args": [5, 5], "expected": 5}],
    },
    # ---- JavaScript loops ----
    {
        "id": "js_loops_sum_1_n",
        "language": "javascript",
        "concept": "loops",
        "skill_id": "js_loops",
        "difficulty": 2,
        "kind": "practice",
        "entry_point": "sumToN",
        "prompt": "Write a function sumToN(n) that returns the sum of integers from 1 to n inclusive.",
        "reference_solution": "function sumToN(n) {\n  let total = 0;\n  for (let i = 1; i <= n; i++) total += i;\n  return total;\n}\n",
        "visible_tests": [{"args": [5], "expected": 15}],
        "hidden_tests": [{"args": [10], "expected": 55}, {"args": [100], "expected": 5050}],
    },
    {
        "id": "js_loops_count_even",
        "language": "javascript",
        "concept": "loops",
        "skill_id": "js_loops",
        "difficulty": 2,
        "kind": "similar",
        "entry_point": "countEven",
        "prompt": "Write countEven(nums) returning how many numbers in the array nums are even.",
        "reference_solution": "function countEven(nums) {\n  let c = 0;\n  for (const x of nums) if (x % 2 === 0) c++;\n  return c;\n}\n",
        "visible_tests": [{"args": [[1, 2, 3, 4]], "expected": 2}],
        "hidden_tests": [{"args": [[2, 4, 6]], "expected": 3}],
    },
]

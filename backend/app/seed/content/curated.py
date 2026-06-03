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
        "exercise_type": "implement_return",
        "entry_point": "sum_to_n",
        "prompt": "Write a function sum_to_n(n) that returns the sum of integers from 1 to n inclusive.",
        "reference_solution": "def sum_to_n(n):\n    total = 0\n    for i in range(1, n + 1):\n        total += i\n    return total\n",
        "visible_tests": [{"args": [5], "expected": 15}, {"args": [1], "expected": 1}],
        "hidden_tests": [{"args": [10], "expected": 55}, {"args": [100], "expected": 5050}],
    },
    {
        "id": "py_loops_trace_accumulator",
        "language": "python",
        "concept": "loops",
        "skill_id": "py_loops",
        "difficulty": 2,
        "kind": "practice",
        "exercise_type": "trace_value",
        "entry_point": "",
        "prompt": (
            "Trace this loop by hand. After it finishes, what is the value of "
            "`total`? Type just the final number."
        ),
        "given_code": "total = 0\nfor i in range(1, 4):\n    total += i",
        "expected_answer": "6",
        "reference_solution": "total = 0\nfor i in range(1, 4):\n    total += i\nprint(total)\n",
        "visible_tests": [],
        "hidden_tests": [],
    },
    {
        "id": "py_loops_predict_range",
        "language": "python",
        "concept": "loops",
        "skill_id": "py_loops",
        "difficulty": 2,
        "kind": "practice",
        "exercise_type": "predict_output",
        "entry_point": "",
        "prompt": "Read the code below. What does it print? Type the exact output.",
        "given_code": "for i in range(3):\n    print(i)",
        "expected_answer": "0\n1\n2",
        "reference_solution": "for i in range(3):\n    print(i)\n",
        "visible_tests": [],
        "hidden_tests": [],
    },
    {
        "id": "py_loops_fix_offbyone",
        "language": "python",
        "concept": "loops",
        "skill_id": "py_loops",
        "difficulty": 3,
        "kind": "similar",
        "exercise_type": "find_the_bug",
        "entry_point": "sum_to_n",
        "prompt": (
            "This function has an off-by-one bug: it should return the sum of "
            "1..n inclusive but it misses the last number. Fix it."
        ),
        "given_code": "def sum_to_n(n):\n    total = 0\n    for i in range(1, n):\n        total += i\n    return total\n",
        "reference_solution": "def sum_to_n(n):\n    total = 0\n    for i in range(1, n + 1):\n        total += i\n    return total\n",
        "visible_tests": [{"args": [5], "expected": 15}],
        "hidden_tests": [{"args": [10], "expected": 55}, {"args": [1], "expected": 1}],
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
    # -----------------------------------------------------------------------
    # Early-skill practice coverage. One practice task per concept for BOTH
    # languages so the adaptive trajectory never starts on an empty skill.
    # Every reference_solution is sandbox-verifiable against its own tests.
    # -----------------------------------------------------------------------
    # ---- Python: variables ----
    # Diversified by exercise_type (Problem 4): the same skill is now practised
    # through DIFFERENT cognitive exercises — implement, predict an output, trace
    # a value, and fix a bug — not three variants of "write a function".
    {
        "id": "py_variables_swap",
        "language": "python",
        "concept": "variables",
        "skill_id": "py_variables",
        "difficulty": 1,
        "kind": "practice",
        "exercise_type": "implement_return",
        "entry_point": "swap",
        "prompt": "Write swap(a, b) that returns a list [b, a] — the two values in swapped order.",
        "reference_solution": "def swap(a, b):\n    return [b, a]\n",
        "visible_tests": [{"args": [1, 2], "expected": [2, 1]}],
        "hidden_tests": [{"args": [9, 4], "expected": [4, 9]}, {"args": [0, 0], "expected": [0, 0]}],
    },
    {
        "id": "py_variables_predict_assign",
        "language": "python",
        "concept": "variables",
        "skill_id": "py_variables",
        "difficulty": 1,
        "kind": "practice",
        "exercise_type": "predict_output",
        "entry_point": "",
        "prompt": (
            "Read the code below. What does it print? Type the exact output."
        ),
        "given_code": "a = 5\nb = a\na = a + 3\nprint(a, b)",
        "expected_answer": "8 5",
        # reference_solution = the given code (its real output IS the answer; the
        # generator/verify path can re-derive expected_answer by running it).
        "reference_solution": "a = 5\nb = a\na = a + 3\nprint(a, b)\n",
        "visible_tests": [],
        "hidden_tests": [],
    },
    {
        "id": "py_variables_trace_swap",
        "language": "python",
        "concept": "variables",
        "skill_id": "py_variables",
        "difficulty": 1,
        "kind": "practice",
        "exercise_type": "trace_value",
        "entry_point": "",
        "prompt": (
            "Trace the code by hand. After it runs, what is the value of `x`? "
            "Type just the final value of x."
        ),
        "given_code": "x = 10\ny = 20\ntmp = x\nx = y\ny = tmp",
        "expected_answer": "20",
        "reference_solution": "x = 10\ny = 20\ntmp = x\nx = y\ny = tmp\nprint(x)\n",
        "visible_tests": [],
        "hidden_tests": [],
    },
    {
        "id": "py_variables_fix_swap",
        "language": "python",
        "concept": "variables",
        "skill_id": "py_variables",
        "difficulty": 2,
        "kind": "practice",
        "exercise_type": "find_the_bug",
        "entry_point": "swap",
        "prompt": (
            "The function below is supposed to return [b, a] but it has a bug. "
            "Fix it so swap(a, b) returns the two values in swapped order."
        ),
        "given_code": "def swap(a, b):\n    return [a, b]\n",
        "reference_solution": "def swap(a, b):\n    return [b, a]\n",
        "visible_tests": [{"args": [1, 2], "expected": [2, 1]}],
        "hidden_tests": [{"args": [9, 4], "expected": [4, 9]}],
    },
    # ---- Python: io ----
    {
        "id": "py_io_greet",
        "language": "python",
        "concept": "io",
        "skill_id": "py_io",
        "difficulty": 1,
        "kind": "practice",
        "exercise_type": "implement_return",
        "entry_point": "greet",
        "prompt": "Write greet(name) that returns the string 'Hello, <name>!' (e.g. greet('Sam') -> 'Hello, Sam!').",
        "reference_solution": "def greet(name):\n    return 'Hello, ' + name + '!'\n",
        "visible_tests": [{"args": ["Sam"], "expected": "Hello, Sam!"}],
        "hidden_tests": [{"args": ["Ada"], "expected": "Hello, Ada!"}, {"args": [""], "expected": "Hello, !"}],
    },
    {
        "id": "py_io_predict_fstring",
        "language": "python",
        "concept": "io",
        "skill_id": "py_io",
        "difficulty": 1,
        "kind": "practice",
        "exercise_type": "predict_output",
        "entry_point": "",
        "prompt": "Read the code below. What does it print? Type the exact output.",
        "given_code": "name = 'Ada'\nprint(f'Hello, {name}!')",
        "expected_answer": "Hello, Ada!",
        "reference_solution": "name = 'Ada'\nprint(f'Hello, {name}!')\n",
        "visible_tests": [],
        "hidden_tests": [],
    },
    {
        "id": "py_io_fill_greet",
        "language": "python",
        "concept": "io",
        "skill_id": "py_io",
        "difficulty": 1,
        "kind": "practice",
        "exercise_type": "fill_in_the_blank",
        "entry_point": "greet",
        "prompt": (
            "Complete the function so greet(name) returns 'Hello, <name>!'. "
            "Replace the ___ blank and submit the full function."
        ),
        "template": "def greet(name):\n    return 'Hello, ' + ___ + '!'\n",
        "reference_solution": "def greet(name):\n    return 'Hello, ' + name + '!'\n",
        "visible_tests": [{"args": ["Sam"], "expected": "Hello, Sam!"}],
        "hidden_tests": [{"args": ["Ada"], "expected": "Hello, Ada!"}],
    },
    # ---- Python: functions ----
    {
        "id": "py_functions_square",
        "language": "python",
        "concept": "functions",
        "skill_id": "py_functions",
        "difficulty": 2,
        "kind": "practice",
        "entry_point": "square",
        "prompt": "Write square(x) that returns x multiplied by itself.",
        "reference_solution": "def square(x):\n    return x * x\n",
        "visible_tests": [{"args": [4], "expected": 16}],
        "hidden_tests": [{"args": [0], "expected": 0}, {"args": [7], "expected": 49}],
    },
    # ---- Python: collections ----
    {
        "id": "py_collections_total",
        "language": "python",
        "concept": "collections",
        "skill_id": "py_collections",
        "difficulty": 2,
        "kind": "practice",
        "entry_point": "list_sum",
        "prompt": "Write list_sum(nums) that returns the sum of all numbers in the list nums (0 for an empty list).",
        "reference_solution": "def list_sum(nums):\n    total = 0\n    for x in nums:\n        total += x\n    return total\n",
        "visible_tests": [{"args": [[1, 2, 3]], "expected": 6}],
        "hidden_tests": [{"args": [[]], "expected": 0}, {"args": [[10, -5]], "expected": 5}],
    },
    # ---- Python: dicts ----
    {
        "id": "py_dicts_get_or_zero",
        "language": "python",
        "concept": "dicts",
        "skill_id": "py_dicts",
        "difficulty": 3,
        "kind": "practice",
        "entry_point": "get_or_zero",
        "prompt": "Write get_or_zero(d, key) that returns d[key] if key is present, otherwise 0.",
        "reference_solution": "def get_or_zero(d, key):\n    return d.get(key, 0)\n",
        "visible_tests": [{"args": [{"a": 1}, "a"], "expected": 1}],
        "hidden_tests": [{"args": [{"a": 1}, "b"], "expected": 0}, {"args": [{}, "x"], "expected": 0}],
    },
    # ---- Python: strings ----
    {
        "id": "py_strings_reverse",
        "language": "python",
        "concept": "strings",
        "skill_id": "py_strings",
        "difficulty": 2,
        "kind": "practice",
        "entry_point": "reverse",
        "prompt": "Write reverse(s) that returns the string s reversed.",
        "reference_solution": "def reverse(s):\n    return s[::-1]\n",
        "visible_tests": [{"args": ["abc"], "expected": "cba"}],
        "hidden_tests": [{"args": [""], "expected": ""}, {"args": ["racecar"], "expected": "racecar"}],
    },
    # ---- Python: errors ----
    {
        "id": "py_errors_safe_div",
        "language": "python",
        "concept": "errors",
        "skill_id": "py_errors",
        "difficulty": 3,
        "kind": "practice",
        "entry_point": "safe_div",
        "prompt": "Write safe_div(a, b) that returns a / b, but returns None if b is 0 (handle the error).",
        "reference_solution": "def safe_div(a, b):\n    try:\n        return a / b\n    except ZeroDivisionError:\n        return None\n",
        "visible_tests": [{"args": [10, 2], "expected": 5.0}],
        "hidden_tests": [{"args": [1, 0], "expected": None}, {"args": [9, 3], "expected": 3.0}],
    },
    # ---- Python: oop ----
    {
        "id": "py_oop_counter",
        "language": "python",
        "concept": "oop",
        "skill_id": "py_oop",
        "difficulty": 4,
        "kind": "practice",
        "entry_point": "counter_after",
        "prompt": (
            "Write a class Counter with a method inc() that increases an internal count "
            "(starting at 0) by 1, and a function counter_after(n) that creates a Counter, "
            "calls inc() n times, and returns the final count."
        ),
        "reference_solution": (
            "class Counter:\n"
            "    def __init__(self):\n"
            "        self.count = 0\n"
            "    def inc(self):\n"
            "        self.count += 1\n\n"
            "def counter_after(n):\n"
            "    c = Counter()\n"
            "    for _ in range(n):\n"
            "        c.inc()\n"
            "    return c.count\n"
        ),
        "visible_tests": [{"args": [3], "expected": 3}],
        "hidden_tests": [{"args": [0], "expected": 0}, {"args": [10], "expected": 10}],
    },
    # ---- Python: comprehensions ----
    {
        "id": "py_comprehensions_squares",
        "language": "python",
        "concept": "comprehensions",
        "skill_id": "py_comprehensions",
        "difficulty": 3,
        "kind": "practice",
        "entry_point": "squares",
        "prompt": "Write squares(n) that returns a list of the squares of 0..n-1 using a list comprehension.",
        "reference_solution": "def squares(n):\n    return [i * i for i in range(n)]\n",
        "visible_tests": [{"args": [4], "expected": [0, 1, 4, 9]}],
        "hidden_tests": [{"args": [1], "expected": [0]}, {"args": [0], "expected": []}],
    },
    # ---- Python: recursion ----
    {
        "id": "py_recursion_fib",
        "language": "python",
        "concept": "recursion",
        "skill_id": "py_recursion",
        "difficulty": 4,
        "kind": "practice",
        "entry_point": "fib",
        "prompt": "Write fib(n) that returns the n-th Fibonacci number recursively. fib(0)==0, fib(1)==1.",
        "reference_solution": "def fib(n):\n    if n < 2:\n        return n\n    return fib(n - 1) + fib(n - 2)\n",
        "visible_tests": [{"args": [6], "expected": 8}],
        "hidden_tests": [{"args": [0], "expected": 0}, {"args": [10], "expected": 55}],
    },
    # ---- Python: modules ----
    {
        "id": "py_modules_sqrt",
        "language": "python",
        "concept": "modules",
        "skill_id": "py_modules",
        "difficulty": 2,
        "kind": "practice",
        "entry_point": "hypotenuse",
        "prompt": (
            "Import the math module and write hypotenuse(a, b) that returns "
            "math.sqrt(a*a + b*b) as a float."
        ),
        "reference_solution": "import math\n\ndef hypotenuse(a, b):\n    return math.sqrt(a * a + b * b)\n",
        "visible_tests": [{"args": [3, 4], "expected": 5.0}],
        "hidden_tests": [{"args": [6, 8], "expected": 10.0}, {"args": [0, 0], "expected": 0.0}],
    },
    # ---- Python: api ----
    {
        "id": "py_api_build_url",
        "language": "python",
        "concept": "api",
        "skill_id": "py_api",
        "difficulty": 4,
        "kind": "practice",
        "entry_point": "build_url",
        "prompt": (
            "When calling APIs you often build query strings. Write build_url(base, params) "
            "that appends params (a dict) to base as 'base?k1=v1&k2=v2', keys in the dict's "
            "insertion order. If params is empty, return base unchanged."
        ),
        "reference_solution": (
            "def build_url(base, params):\n"
            "    if not params:\n"
            "        return base\n"
            "    query = '&'.join(str(k) + '=' + str(v) for k, v in params.items())\n"
            "    return base + '?' + query\n"
        ),
        "visible_tests": [{"args": ["http://x", {"a": 1, "b": 2}], "expected": "http://x?a=1&b=2"}],
        "hidden_tests": [{"args": ["http://x", {}], "expected": "http://x"}, {"args": ["u", {"q": "hi"}], "expected": "u?q=hi"}],
    },
    # ---- Python: project ----
    {
        "id": "py_project_word_count",
        "language": "python",
        "concept": "project",
        "skill_id": "py_project",
        "difficulty": 5,
        "kind": "practice",
        "entry_point": "word_count",
        "prompt": (
            "Mini project: write word_count(text) that returns the number of "
            "whitespace-separated words in text (0 for an empty/blank string)."
        ),
        "reference_solution": "def word_count(text):\n    return len(text.split())\n",
        "visible_tests": [{"args": ["hello world"], "expected": 2}],
        "hidden_tests": [{"args": [""], "expected": 0}, {"args": ["  a  b  c "], "expected": 3}],
    },
    # ---- JavaScript: variables ----
    {
        "id": "js_variables_swap",
        "language": "javascript",
        "concept": "variables",
        "skill_id": "js_variables",
        "difficulty": 1,
        "kind": "practice",
        "exercise_type": "implement_return",
        "entry_point": "swap",
        "prompt": "Write swap(a, b) that returns an array [b, a] — the two values in swapped order.",
        "reference_solution": "function swap(a, b) {\n  return [b, a];\n}\n",
        "visible_tests": [{"args": [1, 2], "expected": [2, 1]}],
        "hidden_tests": [{"args": [9, 4], "expected": [4, 9]}, {"args": [0, 0], "expected": [0, 0]}],
    },
    {
        "id": "js_variables_predict_assign",
        "language": "javascript",
        "concept": "variables",
        "skill_id": "js_variables",
        "difficulty": 1,
        "kind": "practice",
        "exercise_type": "predict_output",
        "entry_point": "",
        "prompt": "Read the code below. What does it print? Type the exact output.",
        "given_code": "let a = 5;\nlet b = a;\na = a + 3;\nconsole.log(a, b);",
        "expected_answer": "8 5",
        "reference_solution": "let a = 5;\nlet b = a;\na = a + 3;\nconsole.log(a, b);\n",
        "visible_tests": [],
        "hidden_tests": [],
    },
    {
        "id": "js_variables_fix_swap",
        "language": "javascript",
        "concept": "variables",
        "skill_id": "js_variables",
        "difficulty": 2,
        "kind": "practice",
        "exercise_type": "find_the_bug",
        "entry_point": "swap",
        "prompt": (
            "The function below should return [b, a] but it has a bug. Fix it so "
            "swap(a, b) returns the two values in swapped order."
        ),
        "given_code": "function swap(a, b) {\n  return [a, b];\n}\n",
        "reference_solution": "function swap(a, b) {\n  return [b, a];\n}\n",
        "visible_tests": [{"args": [1, 2], "expected": [2, 1]}],
        "hidden_tests": [{"args": [9, 4], "expected": [4, 9]}],
    },
    # ---- JavaScript: io ----
    {
        "id": "js_io_greet",
        "language": "javascript",
        "concept": "io",
        "skill_id": "js_io",
        "difficulty": 1,
        "kind": "practice",
        "entry_point": "greet",
        "prompt": "Write greet(name) that returns the string 'Hello, <name>!' (e.g. greet('Sam') -> 'Hello, Sam!').",
        "reference_solution": "function greet(name) {\n  return 'Hello, ' + name + '!';\n}\n",
        "visible_tests": [{"args": ["Sam"], "expected": "Hello, Sam!"}],
        "hidden_tests": [{"args": ["Ada"], "expected": "Hello, Ada!"}, {"args": [""], "expected": "Hello, !"}],
    },
    # ---- JavaScript: conditions ----
    {
        "id": "js_cond_max2",
        "language": "javascript",
        "concept": "conditions",
        "skill_id": "js_conditions",
        "difficulty": 1,
        "kind": "practice",
        "entry_point": "max2",
        "prompt": "Write max2(a, b) returning the larger of two numbers.",
        "reference_solution": "function max2(a, b) {\n  return a > b ? a : b;\n}\n",
        "visible_tests": [{"args": [3, 7], "expected": 7}],
        "hidden_tests": [{"args": [9, 2], "expected": 9}, {"args": [5, 5], "expected": 5}],
    },
    # ---- JavaScript: functions ----
    {
        "id": "js_functions_square",
        "language": "javascript",
        "concept": "functions",
        "skill_id": "js_functions",
        "difficulty": 2,
        "kind": "practice",
        "entry_point": "square",
        "prompt": "Write square(x) that returns x multiplied by itself.",
        "reference_solution": "function square(x) {\n  return x * x;\n}\n",
        "visible_tests": [{"args": [4], "expected": 16}],
        "hidden_tests": [{"args": [0], "expected": 0}, {"args": [7], "expected": 49}],
    },
    # ---- JavaScript: collections ----
    {
        "id": "js_collections_total",
        "language": "javascript",
        "concept": "collections",
        "skill_id": "js_collections",
        "difficulty": 2,
        "kind": "practice",
        "entry_point": "listSum",
        "prompt": "Write listSum(nums) that returns the sum of all numbers in the array nums (0 for an empty array).",
        "reference_solution": "function listSum(nums) {\n  let total = 0;\n  for (const x of nums) total += x;\n  return total;\n}\n",
        "visible_tests": [{"args": [[1, 2, 3]], "expected": 6}],
        "hidden_tests": [{"args": [[]], "expected": 0}, {"args": [[10, -5]], "expected": 5}],
    },
    # ---- JavaScript: dicts (objects) ----
    {
        "id": "js_dicts_get_or_zero",
        "language": "javascript",
        "concept": "dicts",
        "skill_id": "js_dicts",
        "difficulty": 3,
        "kind": "practice",
        "entry_point": "getOrZero",
        "prompt": "Write getOrZero(obj, key) that returns obj[key] if the key exists, otherwise 0.",
        "reference_solution": "function getOrZero(obj, key) {\n  return Object.prototype.hasOwnProperty.call(obj, key) ? obj[key] : 0;\n}\n",
        "visible_tests": [{"args": [{"a": 1}, "a"], "expected": 1}],
        "hidden_tests": [{"args": [{"a": 1}, "b"], "expected": 0}, {"args": [{}, "x"], "expected": 0}],
    },
    # ---- JavaScript: strings ----
    {
        "id": "js_strings_reverse",
        "language": "javascript",
        "concept": "strings",
        "skill_id": "js_strings",
        "difficulty": 2,
        "kind": "practice",
        "entry_point": "reverse",
        "prompt": "Write reverse(s) that returns the string s reversed.",
        "reference_solution": "function reverse(s) {\n  return s.split('').reverse().join('');\n}\n",
        "visible_tests": [{"args": ["abc"], "expected": "cba"}],
        "hidden_tests": [{"args": [""], "expected": ""}, {"args": ["racecar"], "expected": "racecar"}],
    },
    # ---- JavaScript: errors ----
    {
        "id": "js_errors_safe_parse",
        "language": "javascript",
        "concept": "errors",
        "skill_id": "js_errors",
        "difficulty": 3,
        "kind": "practice",
        "entry_point": "safeParse",
        "prompt": (
            "Write safeParse(s) that returns the parsed JSON value of string s, "
            "or null if s is not valid JSON (use try/catch)."
        ),
        "reference_solution": "function safeParse(s) {\n  try {\n    return JSON.parse(s);\n  } catch (e) {\n    return null;\n  }\n}\n",
        "visible_tests": [{"args": ["[1, 2]"], "expected": [1, 2]}],
        "hidden_tests": [{"args": ["not json"], "expected": None}, {"args": ["42"], "expected": 42}],
    },
    # ---- JavaScript: oop ----
    {
        "id": "js_oop_counter",
        "language": "javascript",
        "concept": "oop",
        "skill_id": "js_oop",
        "difficulty": 4,
        "kind": "practice",
        "entry_point": "counterAfter",
        "prompt": (
            "Write a class Counter with a method inc() that increases an internal count "
            "(starting at 0) by 1, and a function counterAfter(n) that creates a Counter, "
            "calls inc() n times, and returns the final count."
        ),
        "reference_solution": (
            "class Counter {\n"
            "  constructor() {\n"
            "    this.count = 0;\n"
            "  }\n"
            "  inc() {\n"
            "    this.count += 1;\n"
            "  }\n"
            "}\n\n"
            "function counterAfter(n) {\n"
            "  const c = new Counter();\n"
            "  for (let i = 0; i < n; i++) c.inc();\n"
            "  return c.count;\n"
            "}\n"
        ),
        "visible_tests": [{"args": [3], "expected": 3}],
        "hidden_tests": [{"args": [0], "expected": 0}, {"args": [10], "expected": 10}],
    },
    # ---- JavaScript: comprehensions (functional map) ----
    {
        "id": "js_comprehensions_squares",
        "language": "javascript",
        "concept": "comprehensions",
        "skill_id": "js_comprehensions",
        "difficulty": 3,
        "kind": "practice",
        "entry_point": "squares",
        "prompt": "Write squares(n) that returns an array of the squares of 0..n-1 using Array.from/map.",
        "reference_solution": "function squares(n) {\n  return Array.from({ length: n }, (_, i) => i * i);\n}\n",
        "visible_tests": [{"args": [4], "expected": [0, 1, 4, 9]}],
        "hidden_tests": [{"args": [1], "expected": [0]}, {"args": [0], "expected": []}],
    },
    # ---- JavaScript: recursion ----
    {
        "id": "js_recursion_fib",
        "language": "javascript",
        "concept": "recursion",
        "skill_id": "js_recursion",
        "difficulty": 4,
        "kind": "practice",
        "entry_point": "fib",
        "prompt": "Write fib(n) that returns the n-th Fibonacci number recursively. fib(0)==0, fib(1)==1.",
        "reference_solution": "function fib(n) {\n  if (n < 2) return n;\n  return fib(n - 1) + fib(n - 2);\n}\n",
        "visible_tests": [{"args": [6], "expected": 8}],
        "hidden_tests": [{"args": [0], "expected": 0}, {"args": [10], "expected": 55}],
    },
    # ---- JavaScript: modules ----
    {
        "id": "js_modules_hypotenuse",
        "language": "javascript",
        "concept": "modules",
        "skill_id": "js_modules",
        "difficulty": 2,
        "kind": "practice",
        "entry_point": "hypotenuse",
        "prompt": (
            "Use the built-in Math object and write hypotenuse(a, b) that returns "
            "Math.sqrt(a*a + b*b)."
        ),
        "reference_solution": "function hypotenuse(a, b) {\n  return Math.sqrt(a * a + b * b);\n}\n",
        "visible_tests": [{"args": [3, 4], "expected": 5}],
        "hidden_tests": [{"args": [6, 8], "expected": 10}, {"args": [0, 0], "expected": 0}],
    },
    # ---- JavaScript: api ----
    {
        "id": "js_api_build_url",
        "language": "javascript",
        "concept": "api",
        "skill_id": "js_api",
        "difficulty": 4,
        "kind": "practice",
        "entry_point": "buildUrl",
        "prompt": (
            "When calling APIs you often build query strings. Write buildUrl(base, params) "
            "that appends params (an object) to base as 'base?k1=v1&k2=v2', keys in insertion "
            "order. If params has no keys, return base unchanged."
        ),
        "reference_solution": (
            "function buildUrl(base, params) {\n"
            "  const keys = Object.keys(params);\n"
            "  if (keys.length === 0) return base;\n"
            "  const query = keys.map((k) => k + '=' + params[k]).join('&');\n"
            "  return base + '?' + query;\n"
            "}\n"
        ),
        "visible_tests": [{"args": ["http://x", {"a": 1, "b": 2}], "expected": "http://x?a=1&b=2"}],
        "hidden_tests": [{"args": ["http://x", {}], "expected": "http://x"}, {"args": ["u", {"q": "hi"}], "expected": "u?q=hi"}],
    },
    # ---- JavaScript: project ----
    {
        "id": "js_project_word_count",
        "language": "javascript",
        "concept": "project",
        "skill_id": "js_project",
        "difficulty": 5,
        "kind": "practice",
        "entry_point": "wordCount",
        "prompt": (
            "Mini project: write wordCount(text) that returns the number of "
            "whitespace-separated words in text (0 for an empty/blank string)."
        ),
        "reference_solution": (
            "function wordCount(text) {\n"
            "  const trimmed = text.trim();\n"
            "  if (trimmed === '') return 0;\n"
            "  return trimmed.split(/\\s+/).length;\n"
            "}\n"
        ),
        "visible_tests": [{"args": ["hello world"], "expected": 2}],
        "hidden_tests": [{"args": [""], "expected": 0}, {"args": ["  a  b  c "], "expected": 3}],
    },
]

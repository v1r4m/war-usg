#!/usr/bin/env python3
import ast
import os
import operator
import random
import multiprocessing
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NoReturn
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# --- judge limits ---
TIMEOUT = 20
MAX_CODE_SIZE = 4096
MAX_SCORE = 16384  
MEMORY_SIZE = 1_000_000
MAX_CYCLES = 1_000_000
# N is fixed by the server.
FORCED_N = 65536

class InterpreterError(Exception): pass
class CompilationError(InterpreterError): pass
class ExecutionError(InterpreterError): pass
class CycleLimitExceeded(ExecutionError): pass

@dataclass
class CycleContext:
    cycles: int = 0
    reads: int = 0
    writes: int = 0
    operations: int = 0
    max_cycles: int | None = None

    def charge_cycle(self) -> None:
        if self.max_cycles is not None and self.cycles >= self.max_cycles:
            raise CycleLimitExceeded(f'cycle limit exceeded ({self.max_cycles})')
        self.cycles += 1

    def charge_read(self): self.charge_cycle(); self.reads += 1
    def charge_write(self): self.charge_cycle(); self.writes += 1
    def charge_op(self): self.charge_cycle(); self.operations += 1

class Value:
    __slots__ = ('value', 'ctx')
    def __init__(self, value: int, ctx: CycleContext):
        self.value = value
        self.ctx = ctx

    @staticmethod
    def _make_op(op, reflected=False, wrap=True, unary=False):
        def meth(self, other=None):
            self.ctx.charge_op()
            if unary: 
                return Value(op(self.value), ctx=self.ctx) if wrap else op(self.value)
            b = other.value if isinstance(other, Value) else other
            if type(b) is not int: 
                raise TypeError('integer expected')
            a = self.value
            if reflected: 
                a, b = b, a
            return Value(op(a, b), ctx=self.ctx) if wrap else op(a, b)
        return meth

    # arithmetic
    __add__ = _make_op(operator.add)
    __radd__ = _make_op(operator.add, reflected=True)
    __sub__ = _make_op(operator.sub)
    __rsub__ = _make_op(operator.sub, reflected=True)
    __mul__ = _make_op(operator.mul)
    __rmul__ = _make_op(operator.mul, reflected=True)
    __floordiv__ = _make_op(operator.floordiv)
    __rfloordiv__ = _make_op(operator.floordiv, reflected=True)
    __mod__ = _make_op(operator.mod)
    __rmod__ = _make_op(operator.mod, reflected=True)
    
    # bitwise
    __or__ = _make_op(operator.or_)
    __ror__ = _make_op(operator.or_, reflected=True)
    __xor__ = _make_op(operator.xor)
    __rxor__ = _make_op(operator.xor, reflected=True)
    __and__ = _make_op(operator.and_)
    __rand__ = _make_op(operator.and_, reflected=True)

    # comparisons
    __eq__ = _make_op(operator.eq, wrap=False)
    __ne__ = _make_op(operator.ne, wrap=False)
    __lt__ = _make_op(operator.lt, wrap=False)
    __le__ = _make_op(operator.le, wrap=False)
    __gt__ = _make_op(operator.gt, wrap=False)
    __ge__ = _make_op(operator.ge, wrap=False)

    # unary
    __neg__ = _make_op(operator.neg, unary=True)
    __pos__ = _make_op(operator.pos, unary=True)

class Memory:
    def __init__(self, size: int, max_cycles: int):
        self.data = [0] * size
        self.ctx = CycleContext(max_cycles=max_cycles)

    def __getitem__(self, index):
        idx = index.value if isinstance(index, Value) else index
        self.ctx.charge_read()
        return Value(self.data[idx], ctx=self.ctx)

    def __setitem__(self, index, value):
        idx = index.value if isinstance(index, Value) else index
        val = value.value if isinstance(value, Value) else value
        self.data[idx] = val
        self.ctx.charge_write()

class Validator(ast.NodeVisitor):
    BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod, ast.BitOr, ast.BitXor, ast.BitAnd)
    UNARYOPS = (ast.UAdd, ast.USub)
    CMPOPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)

    def __init__(self, fn_arg: str):
        self.fn_arg = fn_arg

    def fail(self, node: ast.AST, message: str) -> NoReturn:
        raise CompilationError(f"{message}")

    def visit_function_body(self, fn: ast.FunctionDef) -> None:
        for stmt in fn.body:
            self.visit(stmt)

    def generic_visit(self, node: ast.AST) -> None:
        self.fail(node, f'forbidden syntax: {type(node).__name__}')

    def validate_memory_access(self, node: ast.AST, *, store: bool) -> None:
        if not isinstance(node, ast.Subscript):
            self.fail(node, 'assignment target must be a memory cell')
        expected_context = ast.Store if store else ast.Load
        if not isinstance(node.ctx, expected_context):
            self.fail(node, 'invalid memory access context')
        if not isinstance(node.value, ast.Name) or node.value.id != self.fn_arg:
            self.fail(node, 'target name does not match function parameter')
        if isinstance(node.slice, ast.Slice):
            self.fail(node, 'subscript cannot be a slice')
        self.visit(node.slice)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self.validate_memory_access(target, store=True)
        self.visit(node.value)

    def visit_If(self, node: ast.If) -> None: super().generic_visit(node)
    def visit_While(self, node: ast.While) -> None: super().generic_visit(node)
    def visit_Break(self, node: ast.Break) -> None: super().generic_visit(node)
    def visit_Continue(self, node: ast.Continue) -> None: super().generic_visit(node)
    
    def visit_BinOp(self, node: ast.BinOp) -> None:
        if not isinstance(node.op, self.BINOPS): self.fail(node, 'forbidden arithmetic operator')
        self.visit(node.left); self.visit(node.right)
        
    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if not isinstance(node.op, self.UNARYOPS): self.fail(node, 'forbidden unary operator')
        self.visit(node.operand)
        
    def visit_Compare(self, node: ast.Compare) -> None:
        for op in node.ops:
            if not isinstance(op, self.CMPOPS): self.fail(node, 'forbidden comparison operator')
        self.visit(node.left)
        for comparator in node.comparators: self.visit(comparator)
        
    def visit_Subscript(self, node: ast.Subscript) -> None:
        self.validate_memory_access(node, store=False)
        
    def visit_Constant(self, node: ast.Constant) -> None:
        if type(node.value) is not int: self.fail(node, 'only integer constants are allowed')
        
    def visit_Name(self, node: ast.Name) -> None:
        self.fail(node, 'bare names are forbidden')

class Interpreter:
    def run(self, source: str, initial_memory: list, max_cycles: int):
        tree = ast.parse(source, mode='exec')
        
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            raise CompilationError('program must define exactly one top-level function')
        fn = tree.body[0]
        Validator(fn.args.args[0].arg).visit_function_body(fn)
        
        code = compile(tree, '<string>', 'exec')
        namespace = {}
        exec(code, {'__builtins__': {}}, namespace)
        func = namespace.get(fn.name)
        
        memory = Memory(MEMORY_SIZE, max_cycles=max_cycles)
        for i, val in enumerate(initial_memory):
            memory.data[i] = val
            
        func(memory)
        return memory

def worker(code, score, nums, queue):
    # Online-judge style verdicts. A runtime error reports the exception message as-is.
    try:
        interpreter = Interpreter()
        memory = interpreter.run(code, nums, MAX_CYCLES)

        expected = sorted(nums)
        result = memory.data[:score]

        if result == expected:
            try:
                flag = open('flag.txt', encoding='utf-8', errors='replace').read().strip()
            except OSError:
                flag = None
            queue.put({'verdict': 'Accepted', 'cycles': memory.ctx.cycles, 'flag': flag})
        else:
            queue.put({'verdict': 'Wrong Answer'})
    except CompilationError as e:
        queue.put({'verdict': 'Compile Error', 'detail': str(e)})
    except CycleLimitExceeded as e:
        queue.put({'verdict': 'Time Limit Exceeded', 'detail': str(e)})
    except Exception as e:
        queue.put({'verdict': 'Runtime Error', 'detail': str(e)})

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Sort the Array (Revenge)</title>
    <style>
        body { font-family: -apple-system, 'Segoe UI', sans-serif; margin: 0; background: #f5f6f7; color: #222; }
        .wrap { max-width: 860px; margin: 0 auto; padding: 24px; }
        h1 { font-size: 26px; margin: 0 0 16px; }
        h2 { font-size: 18px; border-bottom: 2px solid #ddd; padding-bottom: 6px; margin: 28px 0 12px; }
        table.limit { border-collapse: collapse; width: 100%; margin-bottom: 12px; font-size: 14px; }
        table.limit th, table.limit td { border: 1px solid #ddd; padding: 8px 10px; text-align: center; }
        table.limit th { background: #fafafa; }
        pre.ex { background: #fff; border: 1px solid #ddd; border-radius: 4px; padding: 10px; overflow-x: auto; }
        p { line-height: 1.65; }
        code { background: #eef1ff; padding: 1px 5px; border-radius: 3px; }
        textarea { width: 100%; box-sizing: border-box; font-family: monospace; font-size: 13px; padding: 8px; }
        button { margin-top: 10px; padding: 9px 24px; font-size: 15px; background: #1b74e4; color: #fff; border: 0; border-radius: 4px; cursor: pointer; }
        #result { margin-top: 16px; }
        .verdict { display: inline-block; padding: 10px 16px; border-radius: 4px; font-weight: bold; font-size: 16px; }
        .ac { background: #d4edda; color: #155724; }
        .wa { background: #f8d7da; color: #721c24; }
        .detail { margin-top: 8px; background: #fff; border: 1px solid #ddd; border-radius: 4px; padding: 10px; white-space: pre-wrap; font-family: monospace; font-size: 13px; }
    </style>
</head>
<body>
<div class="wrap">
    <h1>Sort the Array (Revenge)</h1>
    <table class="limit">
        <tr><th>Time limit</th><th>Cycle limit</th><th>Code length</th><th>N</th></tr>
        <tr><td>20 s</td><td>1,000,000</td><td>4,096 B</td><td>{{ N }}</td></tr>
    </table>

    <h2>Problem</h2>
    <p>You are given an integer array <code>arr</code> of length <strong>N = {{ N }}</strong>. Write a function <code>f(arr)</code> that <strong>sorts the first <code>N</code> elements of <code>arr</code> in place, in non-decreasing order</strong>.</p>
    <p>The only syntax allowed is reading/writing <code>arr[i]</code>, integer arithmetic and bitwise operators, comparisons, and <code>if</code> / <code>while</code>. The array <code>arr</code> has extra scratch space after the first N cells.</p>

    <h2>Input</h2>
    <p><code>arr[0]</code> through <code>arr[N-1]</code> are pre-filled with N unsigned 64-bit integers.</p>

    <h2>Output</h2>
    <p>When the function returns, <code>arr[0] &lt;= arr[1] &lt;= ... &lt;= arr[N-1]</code> must hold.</p>

    <h2>Sample Input 1</h2>
    <pre class="ex">arr = [5, 3, 1, 4, 2]   # when N = 5</pre>
    <h2>Sample Output 1</h2>
    <pre class="ex">arr = [1, 2, 3, 4, 5]</pre>

    <h2>Submit</h2>
    <textarea id="code" rows="14">def f(arr):\n    pass</textarea>
    <br>
    <button onclick="submitCode()">Submit</button>
    <div id="result"></div>
</div>
<script>
    async function submitCode() {
        const box = document.getElementById('result');
        box.innerHTML = '<span class="verdict">Judging…</span>';
        let data;
        try {
            const res = await fetch('/run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ code: document.getElementById('code').value })
            });
            data = await res.json();
        } catch (e) {
            box.innerHTML = '<span class="verdict wa">Judge server error</span>';
            return;
        }
        const ac = data.verdict === 'Accepted';
        let html = '<span class="verdict ' + (ac ? 'ac' : 'wa') + '">' + data.verdict + '</span>';
        if (ac && data.cycles !== undefined) html += ' <small>' + data.cycles + ' cycles</small>';
        if (ac && data.flag) html += '<div class="detail">' + data.flag + '</div>';
        if (data.detail) html += '<div class="detail">' + data.detail + '</div>';
        box.innerHTML = html;
    }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, N=FORCED_N)

@app.route('/run', methods=['POST'])
def run_challenge():
    data = request.json or {}
    code = data.get('code', '')

    if len(code) > MAX_CODE_SIZE:
        return jsonify({'verdict': 'Code Too Long'})

    # N is fixed; the player can't choose it.
    score = FORCED_N

    random.seed(67)
    nums = [random.getrandbits(64) for _ in range(score)]
    
    queue = multiprocessing.Queue()
    proc = multiprocessing.Process(target=worker, args=(code, score, nums, queue))
    proc.start()
    proc.join(TIMEOUT)

    if proc.is_alive():
        proc.terminate()
        proc.join()
        return jsonify({'verdict': 'Time Limit Exceeded'})

    if not queue.empty():
        return jsonify(queue.get())
    return jsonify({'verdict': 'Runtime Error', 'detail': 'unknown execution error'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8000')))

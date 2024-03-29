"""
MIT License

Copyright (c) 2022 AsyncFor

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import os
import ast
import sys
import argparse
from typing import List



def convert_constant(node: ast.Constant):
    if isinstance(node.value, str):
        return f'"{node.value}"'
    elif isinstance(node.value, bool):
        return str(node.value).lower()
    else:
        return str(node.value)


def generate_attribute(node):
    """Converts attribute ast tree to a form like a.b.c"""
    if isinstance(node, ast.Attribute):
        return generate_attribute(node.value) + "." + node.attr
    elif isinstance(node, ast.Call):
        if any([kw for kw in node.keywords if (kw.arg == "nc" or kw.arg == "namecall") and bool(kw.value.value) == True]):
            return unparse_expr(node.func.value) + ":" + node.func.attr + "(" + generate_multiple(node.args) + ")"
        return unparse_expr(node.func) + "(" + generate_multiple(node.args) + ")"
    elif isinstance(node, ast.Constant):
        return str(node.value)
    else:
        return node.id


def generate_multiple(node):
    """Seperates tuple with value"""
    if isinstance(node, ast.Tuple):
        return ", ".join([generate_multiple(n) for n in node.elts])
    elif isinstance(node, ast.List):
        return "[" + generate_multiple(node.elts) + "]"
    elif isinstance(node, list):
        return ", ".join([generate_multiple(n) for n in node])
    elif isinstance(node, ast.Constant):
        return convert_constant(node)
    else:
        return generate_attribute(node)


def generate_for_loop(node: ast.For):
    """
    Converts python for loop to lua for loop
    python for loop example:
    for item in ["hello", "how", "are", "you"]:
        print(item)

    lua for loop example:
    for i,v in pairs({"hello", "how", "are", "you"}) do
        print(v)
    end
    """
    for_loop = f"for _,{generate_multiple(node.target)} in pairs({generate_attribute(node.iter)}) do\n"

    return for_loop


list_comp_count = 0
INDENT = " "*4
definitions = []


def handle_assign(node: ast.Assign, *, is_global=False):
    global definitions
    assignation = "local " if not is_global else ""
    for target in node.targets:
        if isinstance(target, ast.Name):
            if target.id in definitions:
                assignation = unparse_expr(target) + " = "
            else:
                assignation += unparse_expr(target) + " = "
                definitions.append(target.id)
        elif isinstance(target, ast.Attribute):
            target = unparse_expr(target)
            assignation = target + " = "
    if isinstance(node.value, ast.ListComp):
        list_comp, comp_name = handle_list_comp(node.value)
        assignation = list_comp + assignation
        assignation += comp_name
    else:
        assignation += unparse_expr(node.value)
    return assignation


def handle_list_comp(node: ast.ListComp):
    global list_comp_count
    comp_name = f"__list_comp_{list_comp_count}"
    converted_comp = "local " + comp_name + " = {}\n"
    for generator in node.generators:
        if isinstance(generator, ast.comprehension):
            converted_comp += "for _, " + \
                unparse_expr(generator.target) + " in next, " + \
                unparse_expr(generator.iter) + " do\n"
            if len(generator.ifs) > 0:
                current_indention = 1
                for if_expr in generator.ifs:
                    converted_comp += current_indention*INDENT + \
                        "if " + unparse_expr(if_expr) + " then\n"
                    current_indention += 1

                converted_comp += INDENT*current_indention + "table.insert(" + comp_name + \
                    ", " + unparse_expr(node.elt) + ")\n"

                for if_expr in generator.ifs:
                    current_indention -= 1
                    converted_comp += current_indention*INDENT + "end\n"

            else:
                converted_comp += "table.insert(" + comp_name + \
                    ", " + unparse_expr(node.elt) + ")\n"

            converted_comp += "end\n"
    list_comp_count += 1
    return converted_comp, comp_name


def unparse_expr(expr: ast.Expr, *, indent=0):
    indent = " " * indent
    if isinstance(expr, ast.Call):
        if isinstance(expr.func, ast.Name):
            return expr.func.id + "(" + ",".join([unparse_expr(arg) for arg in expr.args]) + ")"
        elif isinstance(expr.func, ast.Attribute):
            if any([kw for kw in expr.keywords if (kw.arg == "nc" or kw.arg == "namecall") and bool(kw.value.value) == True]):
                return unparse_expr(expr.func.value) + ":" + expr.func.attr + "(" + ",".join([unparse_expr(arg) for arg in expr.args]) + ")"
            else:
                return unparse_expr(expr.func.value) + "." + expr.func.attr + "(" + ",".join([unparse_expr(arg) for arg in expr.args]) + ")"
    elif isinstance(expr, ast.Name):
        return expr.id
    elif isinstance(expr, ast.Attribute):
        return generate_attribute(expr)
    elif isinstance(expr, ast.Tuple):
        return generate_multiple(expr)
    elif isinstance(expr, ast.Num):
        return str(expr.n)
    elif isinstance(expr, ast.List):
        return "{" + ",".join([unparse_expr(e) for e in expr.elts]) + "}"
    elif isinstance(expr, ast.Constant):
        if isinstance(expr.value, str):
            return '"' + expr.value + '"'
        elif isinstance(expr.value, bool):
            return str(expr.value).lower()
        elif expr.value is None:
            return "nil"
        else:
            return str(expr.value)

        return f"\"{expr.value}\""
    elif isinstance(expr, ast.Compare):
        return unparse_expr(expr.left) + " " + " ".join([unparse_expr(op) for op in expr.ops]) + " " + unparse_expr(expr.comparators[0])
    elif isinstance(expr, ast.NotEq):
        return "~="
    elif isinstance(expr, ast.Eq):
        return "=="
    elif isinstance(expr, ast.BinOp):
        return unparse_expr(expr.left) + " " + unparse_expr(expr.op) + " " + unparse_expr(expr.right)
    elif isinstance(expr, ast.Mod):
        return "%"
    elif isinstance(expr, ast.BoolOp):
        if isinstance(expr.op, ast.And):
            converted = []
            for v in expr.values:
                converted.append(unparse_expr(v))
                converted.append("and")

            converted.pop(-1)
            return "(" + " ".join(converted) + ")"
        elif isinstance(expr.op, ast.Or):
            converted = []
            for v in expr.values:
                converted.append(unparse_expr(v))
                converted.append("or")

            converted.pop(-1)
            return "(" + " ".join(converted) + ")"
    elif isinstance(expr, ast.UnaryOp):
        return unparse_expr(expr.op) + unparse_expr(expr.operand)
    elif isinstance(expr, ast.Not):
        return "not "
    elif isinstance(expr, ast.Is):
        return "=="
    elif isinstance(expr, ast.Pass):
        return ""
    elif isinstance(expr, ast.Return):
        return "return " + unparse_expr(expr.value)
    elif isinstance(expr, ast.Gt):
        return ">"
    elif isinstance(expr, ast.Lt):
        return "<"
    elif isinstance(expr, ast.GtE):
        return ">="
    elif isinstance(expr, ast.LtE):
        return "<="
    elif isinstance(expr, ast.Await):
        args = [unparse_expr(arg) for arg in expr.value.args]
        return f"coroutine.resume({unparse_expr(expr.value.func) + (', '+','.join(args) if len(args) > 0 else '')})"
    elif isinstance(expr, ast.Lambda):
        return "function(" + ", ".join([arg.arg for arg in expr.args.args]) + ") " + unparse_expr(expr.body) + " end"
    elif isinstance(expr, ast.Add):
        return "+"
    elif isinstance(expr, ast.Sub):
        return "-"
    elif isinstance(expr, ast.Mult):
        return "*"
    elif isinstance(expr, ast.Div):
        return "/"
    elif isinstance(expr, ast.FloorDiv):
        return "//"
    elif isinstance(expr, ast.Dict):
        return "{" + ", ".join(["["+unparse_expr(key)+"]" + " = " + unparse_expr(value) for key, value in zip(expr.keys, expr.values)]) + "}"
    elif isinstance(expr, ast.Set):
        return "{" + ", ".join([unparse_expr(e) for e in expr.elts]) + "}"
    else:
        raise NotImplementedError(expr)


def handle_test(node: ast.Compare):
    return unparse_expr(node.left) + " " + " ".join([unparse_expr(op) for op in node.ops]) + " " + unparse_expr(node.comparators[0])


def is_func_call(node: ast.Expr, *, func_name: str):
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id == func_name
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr == func_name
    return False


def handle_body(body: List[ast.AST], *, indent=0):
    generated_code = ""
    indent = " " * indent
    for node in body:
        if isinstance(node, ast.Assign):
            generated_code += indent + handle_assign(node) + "\n"
        elif isinstance(node, ast.For):

            # if there is only one target, use it directly
            if not isinstance(node.target, ast.Tuple):
                if is_func_call(node.iter, func_name="range"):
                    if len(node.iter.args) == 1:
                        generated_code += indent + \
                            f"for {unparse_expr(node.target)}=1, {unparse_expr(node.iter.args[0])} do\n"""
                    elif len(node.iter.args) == 2:
                        generated_code += indent + \
                            f"for {unparse_expr(node.target)}={unparse_expr(node.iter.args[0])}, {unparse_expr(node.iter.args[1])} do\n"""
                    elif len(node.iter.args) == 3:
                        generated_code += indent + \
                            f"for {unparse_expr(node.target)}={unparse_expr(node.iter.args[0])}, {unparse_expr(node.iter.args[1])}, {unparse_expr(node.iter.args[2])} do\n"""
                else:
                    generated_code += indent + \
                        f"for _, {unparse_expr(node.target)} in next, {unparse_expr(node.iter)} do\n"

            # if there are more than 1 target take tuple
            elif isinstance(node.target, ast.Tuple):
                if isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "enumerate":
                    generated_code += indent + \
                        f"for {unparse_expr(node.target)} in pairs({unparse_expr(node.iter.args[0])}) do\n"
                else:
                    generated_code += indent + \
                        f"for {unparse_expr(node.target)} in {unparse_expr(node.iter)} do\n"

            generated_code += indent + handle_body(node.body, indent=4)
            generated_code += indent + "end\n"
        elif isinstance(node, ast.Expr):
            if isinstance(node, ast.ListComp):
                comp, name = handle_list_comp(node)
                generated_code += indent + comp + "\n"
            else:
                generated_code += indent + unparse_expr(node.value) + "\n"
        elif isinstance(node, ast.If):
            generated_code += indent + "if " + \
                unparse_expr(node.test) + " then\n"
            generated_code += indent + handle_body(node.body, indent=4)
            if node.orelse:
                if isinstance(node.orelse, list):

                    for orelse in node.orelse:
                        generated_code += indent + \
                            f"elseif {unparse_expr(orelse.test)} then\n"
                        generated_code += indent + \
                            handle_body(orelse.body, indent=4)
                        if orelse.orelse:
                            generated_code += indent + "else\n"
                            generated_code += indent + \
                                handle_body(orelse.orelse, indent=4)
                elif isinstance(node.orelse, ast.If):
                    generated_code += indent + "elseif " + \
                        unparse_expr(node.orelse.test) + " then\n"
                    generated_code += indent + \
                        handle_body(node.orelse.body, indent=4)
                else:
                    generated_code += indent + "else\n"
                    generated_code += indent + \
                        handle_body(node.orelse, indent=4)
            generated_code += indent + "end\n"
        elif isinstance(node, ast.While):
            generated_code += indent + "while " + \
                unparse_expr(node.test) + " do\n"
            generated_code += indent + handle_body(node.body, indent=4)
            generated_code += indent + "end\n"
        elif isinstance(node, ast.Pass):
            pass
        elif isinstance(node, ast.Return):
            generated_code += indent + "return " + \
                unparse_expr(node.value) + "\n"
        elif isinstance(node, ast.FunctionDef):
            if "anon" in (dec.id for dec in node.decorator_list) and "local" in (dec.id for dec in node.decorator_list):
                generated_code += indent + \
                    f"local {node.name} = function" + \
                    "(" + \
                    ", ".join([arg.arg for arg in node.args.args]) + ")\n"
                generated_code += indent + handle_body(node.body, indent=4)
                generated_code += indent + "end\n"
            elif "local" in (dec.id for dec in node.decorator_list):
                generated_code += indent + "local function " + node.name + \
                    "(" + \
                    ", ".join([arg.arg for arg in node.args.args]) + ")\n"
                generated_code += indent + handle_body(node.body, indent=4)
                generated_code += indent + "end\n"
            elif "anon" in (dec.id for dec in node.decorator_list):
                generated_code += indent + \
                    "function(" + \
                    ", ".join([arg.arg for arg in node.args.args]) + ")\n"
                generated_code += indent + handle_body(node.body, indent=4)
                generated_code += indent + "end\n"
            else:
                generated_code += indent + "function " + node.name + \
                    "(" + \
                    ", ".join([arg.arg for arg in node.args.args]) + ")\n"
                generated_code += indent + handle_body(node.body, indent=4)
                generated_code += indent + "end\n"
        elif isinstance(node, ast.Try):
            if len(node.handlers) == 1 and len(node.handlers[0].body) == 1 and isinstance(node.handlers[0].body[0], ast.Pass):
                generated_code += indent + "pcall(function()\n"
                generated_code += indent + handle_body(node.body, indent=4)
                generated_code += indent + "end)\n"
            else:
                generated_code += indent + "xpcall(function()\n"
                generated_code += indent + handle_body(node.body, indent=4)
                generated_code += indent + "end, function(err)\n"
                generated_code += indent + handle_body(node.handlers)
                generated_code += indent + "end)\n"
        elif isinstance(node, ast.Break):
            generated_code += indent + "break\n"
        elif isinstance(node, ast.Raise):
            generated_code += indent + \
                "error(" + unparse_expr(node.exc) + ")\n"
        elif isinstance(node, ast.ExceptHandler):
            generated_code += indent + handle_body(node.body, indent=4)
        elif isinstance(node, ast.Import):
            for names in node.names:
                name = names.name
                generated_code += indent + \
                    f"local {names.asname or name} = " + \
                    f"require('{names.name}.lua')\n"
        elif isinstance(node, ast.ImportFrom):
            for names in node.names:
                name = names.name
                if name == "*":
                    generated_code += indent + f"for _, v in next, require('{node.module}.lua') do\n"
                    generated_code += indent + f"    getfenv()[v] = require('{node.module}.lua')[v]\n"
                    generated_code += indent + "end\n"
                else:
                    generated_code += indent + \
                        f"local {names.asname or name} = " + \
                        f"require('{node.module}.lua').{names.name}\n"
        elif isinstance(node, ast.AsyncFunctionDef):
            generated_code += indent + \
                f"local {node.name} = coroutine.create(function({', '.join([arg.arg for arg in node.args.args])})\n"
            generated_code += indent + handle_body(node.body, indent=4)
            generated_code += indent + "end)\n"
        elif isinstance(node, ast.Await):
            generated_code += f"coroutine.resume({unparse_expr(node.value)})\n"
        elif isinstance(node, ast.Lambda):
            generated_code += indent + "function " + \
                unparse_expr(node.args) + "\n"
            generated_code += indent + handle_body(node.body, indent=4)
            generated_code += indent + "end\n"
        elif isinstance(node, ast.AnnAssign):
            if node.annotation.id == "local":
                generated_code += indent + \
                    f"local {unparse_expr(node.target)} = " + \
                    unparse_expr(node.value) + "\n"
        elif isinstance(node, ast.AugAssign):
            generated_code += indent + \
                unparse_expr(node.target) + " = " + \
                unparse_expr(node.target) + " " + \
                unparse_expr(node.op) + " " + \
                unparse_expr(node.value) + "\n"
        else:
            raise NotImplementedError(node)
    return generated_code

__version__ = "0.1.0"
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Translates a Python script to Lua script. Currently supports Python 3.9+.",
        usage=f"python3 {os.path.basename(__file__)} [options] <input> <output>",
        epilog="Version: " + __version__,
        )
    
    parser.add_argument("input", help="Input file to transpile", type=str)
    parser.add_argument("output", help="The transpiled output file", type=str)
    parser.add_argument("-v", "--version", action="version", version=__version__)
    parser.add_argument("-d", "--debug", action="store_true", help="enable debug mode")
    args = parser.parse_args()

    input_file = args.input
    output_file = args.output
    is_debug = args.debug
    with open(input_file, 'r', encoding="utf-8") as f:
        input_py = f.read()

    parsed = ast.parse(input_py)

    root = None
    for node in parsed.body:
        if isinstance(node, ast.FunctionDef):
            if node.name == "main":
                root = node

    if root is None:
        raise Exception("No main function found in the input file")

    if is_debug:    
        print("-"*10, "DUMPED AST TREE", "-"*10)
        print(ast.dump(root, indent=2))
        print("-"*30)

    output = f"-- File auto generated by PyLua v{__version__}\n-- https://github.com/AsyncFor/pyluatranspiler/\n\n" + handle_body(
        root.body)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(output)
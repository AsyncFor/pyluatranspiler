import ast


INPUT_FN = 'input.py'
with open(INPUT_FN, 'r', encoding="utf-8") as f:
    input_py = f.read()

parsed = ast.parse(input_py)

root = parsed.body[0]

print(ast.dump(root, indent=2))

generated_lua = ""


def generate_attribute(node):
    """Converts attribute ast tree to a form like a.b.c"""
    if isinstance(node, ast.Attribute):
        return generate_attribute(node.value) + "." + node.attr
    else:
        return node.id

def generate_multiple(node):
    """Seperates tuple with value"""
    if isinstance(node, ast.Tuple):
        return ", ".join([generate_multiple(n) for n in node.elts])
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
def handle_assign(node: ast.Assign, *, is_global=False):
    assignation = "local " if not is_global else ""
    for target in node.targets:
        assignation += unparse_expr(target) + " = "

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
            converted_comp +=  "for _, " + unparse_expr(generator.target) + " in next, " + unparse_expr(generator.iter) + " do\n"
            if len(generator.ifs) > 0:
                current_indention = 1
                for if_expr in generator.ifs:
                    converted_comp += current_indention*INDENT + "if " + unparse_expr(if_expr) + " then\n"
                    current_indention += 1
                
                converted_comp += INDENT*current_indention + "table.insert(" + comp_name + \
                    ", " + unparse_expr(node.elt) + ")\n"

                for if_expr in generator.ifs:
                    current_indention -= 1
                    converted_comp += current_indention*INDENT + "end\n"
                    
            else:
                converted_comp += "table.insert(" + comp_name + ", " + unparse_expr(node.elt) + ")\n"
            
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
        return f"\"{expr.value}\""
    elif isinstance(expr, ast.Compare):
        return unparse_expr(expr.left) + " " + " ".join([unparse_expr(op) for op in expr.ops]) + " " + unparse_expr(expr.comparators[0])
    elif isinstance(expr, ast.NotEq):
        return "~="

    else:
        raise NotImplementedError(expr)




def handle_body(body: list[ast.AST], *, indent=0):
    generated_code = ""
    indent = " " * indent
    for node in body:
        if isinstance(node, ast.Assign):
            generated_code += indent + handle_assign(node) + "\n"
        elif isinstance(node, ast.For):
            generated_code += indent + f"for _, {unparse_expr(node.target)} in next, {unparse_expr(node.iter)} do\n"
            generated_code += indent + handle_body(node.body, indent = 4)
            generated_code += indent + "end\n"
        elif isinstance(node, ast.Expr):
            if isinstance(node, ast.ListComp):
                comp, name = handle_list_comp(node)
                generated_code += indent + comp + "\n"
            else:
                generated_code += indent + unparse_expr(node.value) + "\n"
            
    return generated_code

output = handle_body(root.body)
with open("output.lua", "w") as f:
    f.write(output)

print(output)
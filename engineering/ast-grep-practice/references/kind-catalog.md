# ast-grep kind catalog

代表的な kind 名のメモ。
Tree-sitter grammar に依存するため、最終確認は必ず `--debug-query=ast` で行う。

```bash
ast-grep run --pattern '<code>' --lang <language> --debug-query=ast
ast-grep run --pattern '<code>' --lang <language> --debug-query=cst
```

## TypeScript / JavaScript

| kind | 例 |
| --- | --- |
| `call_expression` | `foo()` |
| `member_expression` | `obj.prop` |
| `subscript_expression` | `obj['prop']` |
| `import_statement` | `import x from 'x'` |
| `lexical_declaration` | `const x = 1` |
| `variable_declarator` | `x = 1` |
| `function_declaration` | `function f() {}` |
| `arrow_function` | `() => {}` |
| `class_declaration` | `class C {}` |
| `method_definition` | class method |
| `as_expression` | `value as T` |
| `jsx_element` | `<Foo></Foo>` |
| `jsx_self_closing_element` | `<Foo />` |

## Go

| kind | 例 |
| --- | --- |
| `call_expression` | `foo()` |
| `selector_expression` | `pkg.Func` |
| `short_var_declaration` | `x := 1` |
| `var_declaration` | `var x int` |
| `function_declaration` | `func f() {}` |
| `method_declaration` | `func (r R) f() {}` |
| `defer_statement` | `defer f()` |
| `return_statement` | `return x` |
| `if_statement` | `if x {}` |
| `for_statement` | `for ... {}` |
| `import_declaration` | `import "fmt"` |

## Python

| kind | 例 |
| --- | --- |
| `call` | `foo()` |
| `attribute` | `obj.attr` |
| `subscript` | `obj[key]` |
| `function_definition` | `def f():` |
| `class_definition` | `class C:` |
| `assignment` | `x = 1` |
| `import_statement` | `import x` |
| `import_from_statement` | `from x import y` |
| `try_statement` | `try: ...` |
| `except_clause` | `except E:` |
| `with_statement` | `with x:` |

## Dart

Dart は statement 断片だけだと query parse に失敗することがある。
小さな関数や class に包んだ snippet で AST を見て、match できる最小 pattern から始める。

| kind | 例 |
| --- | --- |
| `call_expression` | `print('x')`, `logger.info('x')`, `Navigator.of(context).pop()` |
| `member_expression` | `logger.info`, `Navigator.of(context).pop`, `accountProvider.notifier` |
| `arguments` | call arguments 周辺 |
| `function_declaration` | `void f() {}` |
| `function_signature` | function name / parameters 周辺 |
| `class_declaration` | `class Foo {}` |
| `class_body` | class body 周辺 |
| `import_or_export` | `import 'package:x/x.dart';` |
| `library_import` | import declaration の内側 |
| `const_object_expression` | `const Text('x')` |

Dart の member call は、`logger.info($$$ARGS)` のような dotted pattern がそのまま効かない場合がある。
その場合は `call_expression` の `function` field にある `member_expression` を `object` / `property` で絞る。

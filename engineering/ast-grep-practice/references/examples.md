# ast-grep examples

実践的な rule / test の例。
そのまま catalog として配布するためのものではない。
対象 repository に移すときは、既存 linter で代替できない理由、`files` / `ignores`、severity、message を調整する。

## TypeScript: `as any` を検出する

```yaml
id: no-as-any
language: TypeScript
severity: warning
rule:
  pattern: $EXPR as any
message: as any を使わない。
note: |
  機械的に as unknown へ置換すると型推論や compile error が変わるため fix は付けない。
```

```yaml
id: no-as-any
valid:
  - value as unknown
  - value as User
invalid:
  - value as any
  - JSON.parse(raw) as any
```

## TypeScript: deprecated API を安全に rewrite する

```yaml
id: migrate-old-client-fetch
language: TypeScript
severity: error
rule:
  pattern: oldClient.fetch($URL, $OPTS)
fix: newClient.request($URL, $OPTS)
message: oldClient.fetch は deprecated。newClient.request を使う。
```

```yaml
id: migrate-old-client-fetch
valid:
  - newClient.request(url, opts)
invalid:
  - oldClient.fetch(url, opts)
```

## Go: 特定 API の直接利用を検出する

```yaml
id: no-direct-os-exit
language: Go
severity: warning
rule:
  pattern: os.Exit($CODE)
message: os.Exit を直接呼ばず、project の終了処理 wrapper を使う。
```

```yaml
id: no-direct-os-exit
valid:
  - app.Exit(1)
invalid:
  - os.Exit(1)
```

## Python: `print()` を src 配下で検出する

```yaml
id: no-print-in-src
language: Python
severity: warning
rule:
  pattern: print($$$ARGS)
message: print ではなく logger を使う。
```

```yaml
id: no-print-in-src
valid:
  - logger.info('ok')
invalid:
  - print('debug')
  - print('a', 'b')
```

## Python: bare except を検出する

```yaml
id: no-bare-except
language: Python
severity: warning
rule:
  kind: except_clause
  not:
    has:
      kind: identifier
      stopBy: neighbor
message: bare except を使わず、捕捉する例外を明示する。
```

```yaml
id: no-bare-except
valid:
  - |
    try:
        work()
    except ValueError:
        handle()
invalid:
  - |
    try:
        work()
    except:
        handle()
```

## Dart: debug print を検出する

Dart の statement 断片は query として parse しづらいことがある。
AST を見るときは関数に包んだ snippet から始める。

```bash
ast-grep run --pattern 'void f() { print("x"); }' --lang dart --debug-query=ast
```

```yaml
id: no-debug-print
language: Dart
severity: warning
rule:
  kind: call_expression
  has:
    field: function
    pattern: print
message: print ではなく project の logger を使う。
```

```yaml
id: no-debug-print
valid:
  - void f() { logger.info('ok'); }
invalid:
  - void f() { print('debug'); }
```

## Dart: member call を object / property で絞る

Dart では `logger.info($$$ARGS)` のような dotted pattern が効かない場合がある。
その場合は `call_expression` → `function: member_expression` → `object` / `property` で絞る。

```yaml
id: no-logger-info
language: Dart
severity: warning
rule:
  kind: call_expression
  has:
    field: function
    kind: member_expression
    all:
      - has:
          field: object
          pattern: logger
      - has:
          field: property
          pattern: info
message: logger.info の直接利用を禁止する例。
```

```yaml
id: no-logger-info
valid:
  - void f() { other.info('ok'); }
  - void f() { logger.error('ok'); }
invalid:
  - void f() { logger.info('debug'); }
```

## Dart: chained member call を検出する

`Navigator.of(context).pop()` のような chain は、外側の call の `function` が `member_expression` になり、その `object` が内側の `call_expression` になる。

```yaml
id: no-navigator-pop
language: Dart
severity: warning
rule:
  kind: call_expression
  has:
    field: function
    kind: member_expression
    all:
      - has:
          field: object
          kind: call_expression
          has:
            field: function
            kind: member_expression
            all:
              - has:
                  field: object
                  pattern: Navigator
              - has:
                  field: property
                  pattern: of
      - has:
          field: property
          pattern: pop
message: Navigator.of(context).pop ではなく project の navigation helper を使う。
```

```yaml
id: no-navigator-pop
valid:
  - void f(BuildContext context) { context.pop(false); }
  - void f(BuildContext context) { Navigator.of(context).push(route); }
invalid:
  - void f(BuildContext context) { Navigator.of(context).pop(false); }
```

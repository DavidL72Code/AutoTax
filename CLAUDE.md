# Claude Code Rules

## Security — Never expose secrets
- Never run `cat`, `head`, `tail`, or print any file that may contain secrets (`.env`, `*.pem`, `*credentials*`, `*secret*`, `*key*`, `*token*`).
- Never run any command that prints secret values — no `cat`, `grep` without `-q`, `head`, `tail`, or `print` on sensitive files.
- Never output the value of any secret, API key, private key, token, or password in chat — not even partially.
- To confirm a secret exists: `grep -q "KEY=." .env && echo "set" || echo "missing"` — `-q` suppresses output entirely.

## Token efficiency
- Skip file reads you don't need — prefer `grep` over `Read` when searching for a specific symbol or value.
- Don't read a file back after editing it to verify — edits either succeed or error.
- Don't narrate plans before acting; just act.
- Don't summarize what you just did at the end of a response.
- Avoid redundant tool calls — if one `grep` answers the question, don't also `Read` the same file.
- Prefer single targeted searches over broad exploration; ask for clarification if scope is unclear.
- Don't add comments, docstrings, or explanation to code unless asked.

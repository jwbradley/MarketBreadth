# Security Policy

## This project’s risk profile

MarketBreadth is a set of local scripts that download **public market data** and write **JSON/CSV/logs** on disk. It does not, by default:

- Hold brokerage credentials  
- Place orders  
- Open network ports  
- Require cloud accounts  

## Reporting a vulnerability

If you find a security issue (e.g. unsafe handling of paths, command injection in wrappers, or accidental inclusion of secrets in examples):

1. Prefer a **private** report to the repository maintainer (GitHub Security Advisory if enabled, or the contact listed on the repo).  
2. Please do **not** open a public issue that includes exploit details until a fix is available when the issue is severe.

## What to avoid when forking or deploying

- Do not commit API keys, tokens, or account numbers.  
- Do not point cron logs at world-writable shared paths without access control.  
- Treat downloaded price data as untrusted input (large files, unexpected symbols); keep disk quotas in mind for history JSON growth.  
- If you add paid data APIs later, load secrets from environment variables or a secrets manager—not from the repo.

## Dependencies

Pin or periodically update `yfinance`, `pandas`, and `numpy` in your environment. Report supply-chain issues to those upstream projects as well.

## Disclaimer

Security of your trading capital is separate from software security. See [DISCLAIMER.md](DISCLAIMER.md).

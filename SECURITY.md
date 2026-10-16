# Security policy

FreshMesh is a research prototype. Security reports are welcome, but there is no guaranteed response time, security support contract, or production-hardening claim.

## Supported versions

| Version | Security maintenance |
| --- | --- |
| Current development branch (0.1.x) | Best-effort review and fixes |
| Older commits and downstream forks | No separate backport commitment |

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/ttadev24/FreshMesh/security/advisories/new) **if it is enabled** for this repository. This document does not enable that GitHub setting.

If private reporting is unavailable, check the [maintainer profile](https://github.com/ttadev24) for a private contact method. If none is published, open an issue titled **“Private security contact requested”** containing only a request for a private channel. Do not include vulnerability details, exploit code, credentials, personal information, or affected customer data in that issue.

Include the following privately:

- Affected commit/version, component, and deployment configuration.
- Reproduction steps or a minimal proof of concept using synthetic data.
- Expected and observed behavior, impact, and required privileges.
- Sanitized logs and any suggested mitigation.

Allow time for triage and coordinate disclosure with the maintainer. The project cannot promise a fixed acknowledgement or resolution deadline.

## Relevant security boundaries

Reports involving authentication, chain/store isolation, arbitrary SQL access, assistant tool permissions, approval bypasses, secret exposure, or cross-user data access are especially relevant. Test only on installations and data you are authorized to use.

FreshMesh separates proposed actions from approval. Both direct API calls and agent tools must preserve authorization and audit records. LLM output must be treated as untrusted even when numerical verification succeeds.

## Deployment considerations

- Use a random `FRESHMESH_SECRET` of at least 32 characters outside a disposable local demo. Never expose the development secret or unchanged demo accounts to untrusted users.
- Keep `.env`, `.env.local`, and `web/.env.local` out of version control. The API launcher sources the root `.env.local` as shell code: only use a file you trust.
- `NEXT_PUBLIC_VIETMAP_API_KEY` is embedded in browser assets. Restrict it through the provider. The separate route key, Anthropic key, and Jev key belong only on the server.
- Keep the solver private. Compose binds solver ports to loopback by default. Use appropriate HTTPS, access controls, and network restrictions when hosting beyond localhost.
- Chat passes context and tool outputs to external providers. Review the integration and redaction behavior before using sensitive business data.
- Chat quotas default to 20 turns per client address and 300 globally per day; a configured value of `0` disables that quota. They are not a substitute for deployment-level abuse controls.
- Audit dependency advisories before deployment. Existing project notes identify a Flower constraint on `cryptography<47`; resolve findings against the actual lockfile and installed versions rather than assuming this documentation is a current vulnerability scan.

See [configuration](docs/configuration.md) and [known limitations](docs/limitations.md). Third-party services and datasets have their own policies.

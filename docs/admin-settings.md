# Admin settings

The authenticated settings page at `/admin/settings` edits pipeline provider selection and credentials, role assignments, editorial behavior, and site identity.

## Provider credentials

The provider table shows whether a credential is configured without rendering its value. Entering a password replaces or adds the credential. Leaving the field blank keeps the current value. Select **no key** to clear it; this supports loopback providers that do not require authentication. The test action uses the saved credential and never returns it in the response.

Provider credentials are written to the active `providers.yaml` configuration through the configuration transaction system. Keep that file in the local configuration directory with appropriate filesystem permissions; do not commit a credential-bearing configuration file. Existing `${ENVIRONMENT_VARIABLE}` references remain in place until the credential is replaced or cleared.

For a local OpenAI-compatible server, configure its loopback base URL, model ID, and **local** flag. Add its server key in the credential field when authentication is enabled, or select **no key** when authentication is disabled.

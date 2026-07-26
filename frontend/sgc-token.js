/**
 * Hardcoded Cloud Run identity token for the story genre converter.
 *
 * WHY THIS FILE EXISTS, AND WHY IT IS NOT IN src/
 * ----------------------------------------------
 * The `story-genre-convertor` Cloud Run service has no `allUsers` invoker
 * binding, so every request needs `Authorization: Bearer <identity-token>`.
 * A browser cannot supply that directly: CORS preflight (OPTIONS) is sent
 * WITHOUT the Authorization header by specification, so Cloud Run rejects the
 * preflight with 403 before the token is ever read. Putting the token in
 * client code therefore cannot work, no matter how it is stored.
 *
 * Instead the token is attached by the Vite dev proxy (see vite.config.js),
 * server-side, on the way out. The browser calls same-origin `/sgc/*`, so no
 * preflight happens at all. This module is imported ONLY by vite.config.js and
 * never by anything under src/, so the token is not bundled into the client.
 *
 * THE TOKEN EXPIRES AFTER ~1 HOUR. Refresh it with:
 *
 *     cd frontend && npm run sgc:token
 *
 * The permanent fix is to make the service public, which needs roles/run.admin
 * or roles/owner (the deploying account only has roles/editor, which is why
 * `deploy.sh --allow-unauthenticated` silently failed):
 *
 *     gcloud run services add-iam-policy-binding story-genre-convertor \
 *       --region us-central1 --project pocketfm-hackathon \
 *       --member allUsers --role roles/run.invoker
 *
 * Once that lands, set VITE_SGC_URL to the service URL and this file and the
 * /sgc proxy can both be deleted.
 */

export const SGC_TARGET = 'https://story-genre-convertor-v4c7wg52ia-uc.a.run.app'

export const SGC_TOKEN =
  'eyJhbGciOiJSUzI1NiIsImtpZCI6IjMwZmUwZTIzYzRkNmUzNmM1MjU3N2IxZTJmZWZkMWFiYzM4ODk1ZGUiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20iLCJhenAiOiIzMjU1NTk0MDU1OS5hcHBzLmdvb2dsZXVzZXJjb250ZW50LmNvbSIsImF1ZCI6IjMyNTU1OTQwNTU5LmFwcHMuZ29vZ2xldXNlcmNvbnRlbnQuY29tIiwic3ViIjoiMTAyOTMyNjA5NDQ4ODE3ODA5NzYyIiwiZW1haWwiOiJzYWhpbHRvbWFyMTAwMzAzQGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJhdF9oYXNoIjoicnN6eWt6NnF0b1ptYTZSeUZWNVAzdyIsImlhdCI6MTc4NDk5NjY3MywiZXhwIjoxNzg1MDAwMjczfQ.Fx8S8ifEbMIUacZYGcQ5_2ap5djj5Vc2GbsmqbBy1mQ6xVCpKYEeZAF1wpWeF7rUIeGGX_LX5-p7iZPxGSNfoKaUrLICKChIfNWtW7Ii_SRhpvDLnlN760-bUSlt74tyuyFNQxWd9lt3DJK9ruBq-DyrawRX9NOODo1rNFuVZvpghj_ife3bnvlMbNAF-ylfIbnI1pPy6OWHjIQ5OjGFkwmBhf267lft4JfANK3IcbfGbXgeP1_mM7GV_SCizecaxuTKBwZVz190l59OPv4z3HnedP2cWZkcdgXFYDIX8cElg-V1rbaUnFobNvfQvsZETZzH0cpGafSyh074hz4AYg'

# Email masking utility dependency impact

## Findings before implementation

Superset exposes email addresses through several dependency groups. The masking utility belongs in `@superset-ui/core` so frontend display components, loggers, analytics adapters, templates, serializers, and audit sinks can share one stable masking rule instead of reimplementing local variants.

## Masking contract

- Display and telemetry value: `first-character + *** + @domain`, for example `jdoe@example.com` becomes `j***@example.com`.
- Empty values remain empty so optional UI fields and serializers keep their existing null/empty behavior.
- Malformed email-like values become `***` to avoid leaking raw identifiers.
- Raw email values remain available only through explicitly named `raw` fields returned by `getMaskedEmail` for internal flows that must deliver email, validate email, or serialize the API contract.
- `mailto` values are generated from the raw address and URL-encoded, preserving link functionality without requiring display text to contain the raw email.

## Downstream dependencies affected

| Dependency group | Affected paths | Safe propagation rule |
| --- | --- | --- |
| Frontend/UI components | Owner selection labels, list filters, modal labels, reusable table/list renderers that show user email metadata | Use `maskEmail` for visible text. Keep raw values in explicitly internal form state only when needed for selected values or submissions. |
| Event loggers | UI event payload builders, backend event loggers, browser analytics wrappers | Emit the masked value for human-readable properties. Emit stable non-email identifiers when correlation is required. Do not add raw email to new event payloads. |
| Analytics pipelines | Downstream consumers of event-log payloads, exported usage events, warehouse jobs | Treat masked email as presentation metadata. Use user IDs or UUIDs for joins rather than parsing masked strings. |
| Email/calendar templates | Alert/report templates, invite text, calendar descriptions, notification previews | Use raw email for delivery headers and recipient routing. Use masked email in preview text, logs, rendered recipient summaries, and screenshots. |
| API serializers/deserializers | REST responses that already expose `email`, related-owner endpoints, request payloads that accept recipients | Preserve existing `email` fields for backward compatibility. Add masked companions only in future additive changes; never replace a persisted or submitted raw email field with a masked value. |
| Audit/logging systems | Security audit records, application logs, task logs, notification logs | Log masked values for display. Keep raw addresses out of log context unless a lower-level mail library requires them for delivery and the log sink is access-controlled. |
| Internal raw-email flows | Authentication, user lookup, permission checks, notification delivery, import/export persistence | Continue using raw emails. Avoid feeding masked strings into validators, database filters, recipient lists, or serialized import/export payloads. |

## Implementation notes

- `maskEmail` and `getMaskedEmail` were added to `@superset-ui/core` as the single frontend/shared implementation.
- `OwnerSelectLabel` was updated to mask visible owner email text while preserving caller-provided raw email data for existing select values and save flows.
- Tests cover valid addresses, whitespace normalization, malformed values, optional values, raw/masked separation, and `mailto` encoding.

## Compatibility and integrity assessment

- Backward compatibility: preserved because the utility is additive and existing API payload fields are unchanged.
- API contract stability: preserved because no serializer/deserializer fields were renamed or repurposed.
- Serialization integrity: preserved because masking is applied only at display-helper boundaries in this change.
- Mailto/link functionality: preserved through `getMaskedEmail().mailto`, which is built from the normalized raw email.
- Internal raw-email processing: preserved by keeping raw values explicitly separate from masked display strings.

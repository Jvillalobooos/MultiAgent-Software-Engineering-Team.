# API Design Guidelines

## Resource and endpoint design

Model endpoints around bounded resources and explicit user goals. State the HTTP method, path, request fields, response shape, and status codes. Avoid exposing internal identifiers or persistence details without a business need. Collection endpoints must apply stable ordering, explicit limits, and pagination rules where relevant. A transaction-history response should return only the authorized user's records and enforce the required maximum at the query boundary.

## Input and output contracts

Validate types, formats, ranges, required fields, and unexpected input before domain processing. Use structured error responses that distinguish invalid input, unauthenticated access, forbidden access, missing resources, and internal failure without revealing secrets. Outputs should be minimal, deterministic, and compatible with declared schemas. Never return fields merely because they exist in storage.

## Authorization and abuse controls

Authentication establishes identity; authorization must be checked for the requested object and action. Never trust a user identifier from a path or query without comparing it with the authenticated principal or an approved policy. Apply rate limits to sensitive operations such as password recovery and authentication. Reset tokens must be random, single-use, narrowly scoped, stored safely, and expire within the business-defined lifetime.

## Change and validation

Document API and data implications for every proposal. Cover success, validation failures, ownership failures, empty collections, limits, ordering, repeated requests, and dependency errors. Preserve correlation identifiers and safe operational logs. Backward-incompatible changes require an explicit migration decision; otherwise keep existing consumers working and restrict the patch to the smallest inspected surface.

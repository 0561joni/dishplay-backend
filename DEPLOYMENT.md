# Deployment Notes

## Supabase Configuration

If you encounter `'dict' object has no attribute 'headers'` errors during startup, you may need to configure database timeouts in your Supabase dashboard:

1. Go to your Supabase project dashboard
2. Navigate to the SQL Editor
3. Run this query to set the statement timeout for the authenticated role:

```sql
ALTER ROLE authenticated SET statement_timeout = '10s';
```

This is required even when using the service_role API key, as the timeout configuration affects the underlying PostgREST client.

For more details, see: https://supabase.com/docs/guides/database/postgres/configuration#changing-the-default-timeout
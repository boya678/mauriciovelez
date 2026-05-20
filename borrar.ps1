$body = @{
    "match[]" = '{namespace="mauriciovelez"}'
}

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8481/delete/0/prometheus/api/v1/admin/tsdb/delete_series" `
    -Body $body
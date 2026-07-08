# Checklist operativo de automatizacion Axis

## Estado actual

- OneDrive: listo para validacion tecnica si el archivo compartido, el usuario y los nombres de hojas estan correctos en `.env`.
- WooCommerce Colombia y Mexico: listos para prueba tecnica.
- Meta Ads: listo para prueba tecnica si las cuentas por pais ya estan correctas.
- Shopify Bali: listo para importar ventas web y pedidos.
- Google Ads: pendiente de aprobacion del propietario.

## Comandos para hoy

```bash
python manage.py validate_axis_integrations
python manage.py sync_axis_daily_data --date 2026-05-11 --dry-run
```

## Orden recomendado de avance

1. Validar configuracion sin exponer secretos.
2. Probar WooCommerce Colombia sin persistencia.
3. Probar WooCommerce Mexico sin persistencia.
4. Probar OneDrive WhatsApp Colombia.
5. Probar OneDrive Ecuador.
6. Probar Meta Ads por pais con reglas de ejemplo ajustadas.
7. Probar Shopify Bali.
8. Dejar Google Ads para la fase siguiente cuando llegue la aprobacion.

## Criterio de cierre por fuente

- salida JSON consistente con el dato manual
- segunda corrida sin duplicados
- valores en COP correctos
- categorias bien mapeadas
- notas y `source_file` poblados

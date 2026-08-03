"""Borra los datos de prueba de Tareas y Metas, y desactiva una marca vacia.

Las 162 filas de Tareas y Metas eran pruebas del propio usuario; lo confirmo el
3-ago-2026 y autorizo borrarlas. Se borran los datos, no los modelos: `WeeklyTask` y
`Task` estan conectados a /api/tasks/ y al importador de Excel, asi que retirar las
clases es un cambio aparte y mas amplio.

`marketplaces` (id 7) es una unidad creada por error: 3 canales vacios, cero ventas,
cero pauta y ningun pais. La buena es `marketplace`. Se desactiva en vez de borrarse:
desactivar la saca del filtro sin perder el rastro de que existio.
"""
from django.db import migrations

TEST_MODELS = (
    "UserTaskAttachment", "UserTaskLink", "UserTask",
    "OperationalGoalTaskAttachment", "OperationalGoalTask",
    "InsightAchievement", "SalesTarget", "AgendaTask", "WeeklyTask", "Task",
)


def clean_up(apps, schema_editor):
    for name in TEST_MODELS:
        try:
            model = apps.get_model("reports", name)
        except LookupError:
            continue
        borradas = model.objects.all().delete()
        print(f"    {name}: {borradas}")

    BusinessUnit = apps.get_model("reports", "BusinessUnit")
    vacia = BusinessUnit.objects.filter(slug="marketplaces").first()
    if vacia:
        vacia.is_active = False
        vacia.save(update_fields=["is_active", "updated_at"])
        print(f"    BusinessUnit 'marketplaces' (id {vacia.id}) desactivada")


class Migration(migrations.Migration):
    dependencies = [("reports", "0058_ugc_sample_channel")]
    # Sin reversa: los datos borrados eran pruebas y no hay a que volver.
    operations = [migrations.RunPython(clean_up, migrations.RunPython.noop)]

import openpyxl
from django.http import HttpResponse
from django.utils import timezone
from django.db import models
from datetime import datetime, date

def export_queryset_to_excel(queryset, model):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = str(model._meta.verbose_name_plural)[:31]
    
    # Get all fields
    fields = [f for f in model._meta.fields]
    
    # Header
    ws.append([str(f.verbose_name).title() for f in fields])
    
    for obj in queryset:
        row = []
        for field in fields:
            value = getattr(obj, field.name)
            
            if isinstance(field, models.ForeignKey) and value:
                value = str(value)
            elif isinstance(value, (datetime, date)):
                # Convert to naive for Excel if it has timezone
                if isinstance(value, datetime) and timezone.is_aware(value):
                    value = timezone.localtime(value).replace(tzinfo=None)
            elif field.choices:
                display_method = f'get_{field.name}_display'
                if hasattr(obj, display_method):
                    value = getattr(obj, display_method)()
            
            if value is None:
                value = ""
            
            # Ensure value is something openpyxl can handle
            if not isinstance(value, (str, int, float, datetime, date, bool)):
                value = str(value)
                
            row.append(value)
        ws.append(row)
        
    return wb

def get_excel_response(workbook, filename):
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response

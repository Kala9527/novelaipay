import csv
import io
from collections.abc import Iterable
from datetime import timedelta, timezone

from fastapi.responses import StreamingResponse


def beijing_time(value):
    if not value:
        return ''
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')


def csv_response(filename: str, columns: list[str], rows: Iterable[tuple]) -> StreamingResponse:
    def generate():
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        yield '\ufeff'
        writer.writerow(columns)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        for row in rows:
            writer.writerow(["'" + value if isinstance(value, str) and value.startswith(
                ('=', '+', '-', '@', '\t', '\r', '\n')) else value for value in row])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(generate(), media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"',
                 'Cache-Control': 'no-store'})

import os
import inngest
from dotenv import load_dotenv
from services.ingest import ingest_pdf

load_dotenv()

inngest_client = inngest.Inngest(
    app_id="pdf-chat-agent",
    event_key=os.getenv("INNGEST_EVENT_KEY", "local"),
    signing_key=os.getenv("INNGEST_SIGNING_KEY"),
    is_production=False,
)


@inngest_client.create_function(
    fn_id="process-pdf",
    trigger=inngest.TriggerEvent(event="pdf/ingest"),
)
async def process_pdf(ctx: inngest.Context, step: inngest.Step) -> dict:
    file_path = ctx.event.data["file_path"]
    pdf_id = ctx.event.data["pdf_id"]
    filename = ctx.event.data.get("filename", "")

    result = await step.run(
        "ingest-pdf-chunks",
        lambda: ingest_pdf(file_path, pdf_id, filename),
    )
    return result

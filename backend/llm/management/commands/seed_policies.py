"""
python manage.py seed_policies [--dir PATH]

Loads every *.md file in backend/llm/policies (or --dir) as a policy document, using the CURRENT embedder
(LLM_EMBEDDER) and chunk settings. Each file goes through the same checks as an upload (type, size, UTF-8, no personal
details). Safe to run again: an unchanged file is skipped, a changed file replaces the old version (same file name
and embedder). Prints counts and the time taken, never the file contents.
"""
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from llm import embeddings, extract, ingest, privacy
from llm.models import PolicyDocument
from llm.providers import ProviderError

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "policies"


class Command(BaseCommand):
    help = "Load the fictional HealthProfile demo policies (backend/llm/policies/*.md) for the FAQ assistant."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(DEFAULT_DIR), help="Folder of .md policy files.")

    def handle(self, *args, **options):
        folder = Path(options["dir"])
        files = sorted(folder.glob("*.md"))
        if not files:
            raise CommandError(f"No .md files found in {folder}")
        model_id = embeddings.get_embedder().model_id
        counts = {"added": 0, "replaced": 0, "unchanged": 0}
        started = time.perf_counter()
        for path in files:
            try:
                extracted = extract.extract_text(path.name, path.read_bytes())
            except extract.ExtractError as exc:
                raise CommandError(f"{path.name}: {exc}") from None
            if privacy.contains_personal_details(extracted.text):
                raise CommandError(f"{path.name}: {privacy.DOCUMENT_MESSAGE}")
            existing = PolicyDocument.objects.filter(filename=path.name, embedding_model=model_id).first()
            if existing is not None and existing.sha256 == ingest.content_sha256(extracted.text):
                counts["unchanged"] += 1
                continue
            try:
                with transaction.atomic():
                    if existing is not None:
                        existing.delete()
                    ingest.ingest_document(filename=path.name, title=extracted.title, text=extracted.text,
                                           source="seed")
            except ingest.DuplicateDocument:
                raise CommandError(f"{path.name}: the same content is already stored under another name") from None
            except ProviderError as exc:
                raise CommandError(f"The embedding model failed ({type(exc).__name__}); nothing was changed "
                                   f"for {path.name}.") from None
            counts["replaced" if existing is not None else "added"] += 1
        seconds = time.perf_counter() - started
        self.stdout.write(f"embedder: {model_id} | files: {len(files)} | added: {counts['added']} | "
                          f"replaced: {counts['replaced']} | unchanged: {counts['unchanged']} | "
                          f"time: {seconds:.1f} s")

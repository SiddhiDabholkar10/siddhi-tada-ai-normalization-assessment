"""Local entry point. Transformation output schema is chosen by the candidate."""
import argparse
import json
import sys
from datetime import date, datetime, timezone
from importlib import import_module
from pathlib import Path

from .adapters import ADAPTERS, ENTITIES
from .canonical.schema_export import write_schemas
from .employees.bundle import load_bundle
from .fixtures.write import DEFAULT_SEED, write_fixtures
from .live import client as live_client
from .live.fetch import PLANS, bundle_text, fetch_tenant
from .mappings.render import write_mappings
from .output import build_document, document_text
from .pipeline import normalize_bundle
from .references import all_readiness_issues

LIVE_DIR = "live_data"  # Git-ignored: live output and bundles are personal data (D-009, D-092)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tada AI normalization")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-providers")
    commands.add_parser("check-inputs", help="check the distributed reference pack (contracts/) for each provider")
    run = commands.add_parser(
        "normalize",
        help="normalize a provider bundle to canonical records (sensitive values masked unless --show-sensitive)",
    )
    run.add_argument("--input", type=Path, required=True, help="provider bundle, e.g. fixtures/prismhr/bundle.json")
    run.add_argument("--provider", choices=ADAPTERS, help="optional: must match the provider the bundle names")
    run.add_argument(
        "--entity", choices=ENTITIES, action="append",
        help=(
            "mapping table whose record lists to output (repeatable; payroll gives payroll_runs and paychecks); "
            "default: all. The link check always covers every record of the run"
        ),
    )
    run.add_argument("--output", type=Path, help="file to create (refuses to overwrite); default: standard output")
    run.add_argument("--show-sensitive", action="store_true", help="show sensitive values in full (D-036 opt-in)")
    live = commands.add_parser(
        "fetch",
        help="sign in to a demo tenant, fetch its data, normalize it and write the output (D-092; masked unless --show-sensitive)",
    )
    live.add_argument("--tenant", choices=live_client.TENANTS, required=True, help="demo tenant: prism, isol or ukg")
    live.add_argument("--company", action="append",
                      help="only this company (PrismHR client, isolved legal, UKG company id); repeatable; default: all")
    live.add_argument("--pay-from", type=date.fromisoformat, help="payroll window start (with --pay-to); default: the 12 months "
                      "ending on each company's latest pay date on or before today")
    live.add_argument("--pay-to", type=date.fromisoformat, help="payroll window end (with --pay-from)")
    live.add_argument("--as-of", type=date.fromisoformat, help="the date treated as today (window search, premium date); default: today")
    live.add_argument("--output", type=Path, help=f"file to create (refuses to overwrite); default: {LIVE_DIR}/<provider>-<UTC time>.json")
    live.add_argument("--save-bundle", action="store_true",
                      help="also write the raw responses as a bundle next to the output (personal data; credentials scrubbed)")
    live.add_argument("--show-sensitive", action="store_true", help="show sensitive values in full (D-036 opt-in)")
    live.add_argument("--workers", type=int, default=4, help="calls in parallel (default 4)")
    serve = commands.add_parser("serve", help="start the web app and API (Phase 7b; masked unless a request opts in)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--db", type=Path, default=Path(LIVE_DIR) / "app.db", help=f"app store (personal data); default {LIVE_DIR}/app.db")
    imported = commands.add_parser("import-output", help="load an output document (normalize or fetch) into the app store")
    imported.add_argument("document", type=Path)
    imported.add_argument("--db", type=Path, default=Path(LIVE_DIR) / "app.db")
    from_bundle = commands.add_parser(
        "import-bundle", help="normalize a provider bundle (e.g. a fetch --save-bundle file) into the app store, full values kept")
    from_bundle.add_argument("bundle", type=Path)
    from_bundle.add_argument("--db", type=Path, default=Path(LIVE_DIR) / "app.db")
    writer = commands.add_parser(
        "write", help="dry run: the provider requests that would create or update an employee (D-100; nothing is sent)")
    writer.add_argument("--input", type=Path, required=True, help="provider bundle the employee comes from")
    writer.add_argument("--employee", required=True, help="canonical employee id, e.g. ukg-ready:900003:employee:7001:1101")
    writer.add_argument("--to", required=True, choices=("ukg-ready", "isolved", "prismhr"), help="destination provider")
    writer.add_argument("--operation", choices=("create", "update"), default="create")
    writer.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                        help="destination input (repeatable): company, username, employee, peo_start_date, manager, "
                             "employment_status, employment_category, employment_type, pay_type, pay_frequency, pay_group, "
                             "work_location, job, id_type, legal")
    writer.add_argument("--show-sensitive", action="store_true", help="show sensitive values in full (D-036 opt-in)")
    export = commands.add_parser("export-schemas", help="write the canonical JSON Schema files")
    export.add_argument("--out", type=Path, default=Path("schemas"))
    mappings = commands.add_parser("export-mappings", help="write the mapping documents from the mapping tables")
    mappings.add_argument("--out", type=Path, default=Path("docs/mappings"))
    fixtures = commands.add_parser("generate-fixtures", help="write the synthetic provider bundles and their manifest")
    fixtures.add_argument("--seed", type=int, default=DEFAULT_SEED)
    fixtures.add_argument("--out", type=Path, default=Path("fixtures"))
    args = parser.parse_args(argv)
    if args.command == "normalize":
        return _normalize(args)
    if args.command == "fetch":
        if (args.pay_from is None) != (args.pay_to is None) or (args.pay_from and args.pay_from > args.pay_to):
            parser.error("--pay-from and --pay-to go together, from on or before to")
        if args.workers < 1:
            parser.error("--workers must be at least 1")
        return _fetch(args)
    if args.command == "serve":
        return _serve(args)
    if args.command == "import-output":
        from .app.store import Store  # the app's packages load only for app commands

        try:
            document = json.loads(args.document.read_text(encoding="utf-8"))
            store = Store(args.db)
            try:
                dataset = store.add_document(document, f"Imported: {args.document.name}")
            finally:
                store.close()
        except (OSError, ValueError, KeyError) as exc:
            print(f"error: {exc}; nothing imported", file=sys.stderr)
            return 1
        print(f"dataset {dataset}: {args.document.name} ({document['run']['provider']}, values {document['run']['sensitive_values']})")
        return 0
    if args.command == "write":
        return _write(args)
    if args.command == "import-bundle":
        from .app.store import Store

        try:  # the same pipeline as normalize; the store keeps full values and the API masks them (D-098)
            result = normalize_bundle(load_bundle(args.bundle))
            store = Store(args.db)
            try:
                dataset = store.add_run(result, "import", f"Imported: {args.bundle.name}", args.bundle.name)
            finally:
                store.close()
        except (OSError, ValueError) as exc:
            print(f"error: {exc}; nothing imported", file=sys.stderr)
            return 1
        print(f"dataset {dataset}: {args.bundle.name} (full values: personal data, keep {args.db} out of Git)")
        return 0
    if args.command == "generate-fixtures":
        for path in write_fixtures(args.out, args.seed):
            print(path)
        return 0
    if args.command == "list-providers":
        print("\n".join(ADAPTERS))
        return 0
    if args.command == "export-schemas":
        for path in write_schemas(args.out):
            print(path)
        return 0
    if args.command == "export-mappings":
        for path in write_mappings(args.out):
            print(path)
        return 0
    issues = all_readiness_issues()  # check-inputs
    print(json.dumps(issues, indent=2))
    return 2 if any(issues.values()) else 0


def _normalize(args) -> int:
    """Bundle in, one output document out (D-085, D-087): every record validated by ``to_json``
    and the whole document built before anything is written, masked by default (D-036). Link
    problems go to ``run.link_problems`` and standard error; they do not fail the run."""
    try:
        bundle = load_bundle(args.input)  # read with parse_source_json (exact decimals, D-025)
        provider = args.provider or bundle.provider.value
        # The provider's adapter checks that the bundle is its own (an explicit --provider must match).
        document = ADAPTERS[provider].normalize(
            args.entity, bundle, None, show_sensitive=args.show_sensitive, input_name=args.input.name
        )
        text = document_text(document)
        if args.output is None:
            sys.stdout.write(text)
        else:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # an adapter fault: a clean failure, never a partial file (D-089)
        print(f"error: normalization failed ({type(exc).__name__}: {exc}); nothing written", file=sys.stderr)
        return 1
    for problem in document["run"]["unusable_responses"]:
        print(f"response set aside: {problem}", file=sys.stderr)
    for problem in document["run"]["link_problems"]:
        print(f"link problem: {problem}", file=sys.stderr)
    if args.show_sensitive:
        print("warning: sensitive values are shown in full (--show-sensitive)", file=sys.stderr)
    return 0


def _write(args) -> int:
    """Dry run of a write (D-100): normalize the bundle, take one employee, print the plan.
    Exit 0 when the plan has no refusals, 2 when it has (they are listed in the plan)."""
    from .output import record_json
    from .write import WriteRequest, build

    try:
        inputs = dict(item.split("=", 1) for item in args.set)
    except ValueError:
        print("error: --set takes NAME=VALUE", file=sys.stderr)
        return 1
    try:
        result = normalize_bundle(load_bundle(args.input))
        employees = {record.id: record for record in result.records["employees"]}
        if args.employee not in employees:
            raise ValueError(f"no employee {args.employee!r} in {args.input.name}")
        employee = record_json(employees[args.employee], show_sensitive=True)  # full values, as a write needs
        company = next((record_json(c, show_sensitive=True) for c in result.records["companies"] if c.id == employee.get("company_id")), None)
        plan = build(WriteRequest(args.to, args.operation, employee, company, inputs))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(document_text(plan.view(args.show_sensitive)))
    for refusal in plan.refusals:
        print(f"refused: {refusal['field']}: {refusal['reason']}", file=sys.stderr)
    if args.show_sensitive:
        print("warning: sensitive values are shown in full (--show-sensitive)", file=sys.stderr)
    return 2 if plan.refusals else 0


def _serve(args) -> int:
    """The web app (Phase 7b). Samples are normalized into the store on start; the access log is
    off because URLs carry record ids (logs give counts only)."""
    import logging

    import uvicorn

    from .app.api import create_app
    from .app.store import Store

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = create_app(Store(args.db))
    print(f"app: http://{args.host}:{args.port}  (store {args.db}: personal data, keep out of Git)", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, access_log=False, log_level="info")
    return 0


def write_new(files: list[tuple[Path, str]]) -> None:
    """Create every file, or none: when one write fails, the files this call created are removed
    and the error is raised (D-092 review)."""
    created: list[Path] = []
    try:
        for path, text in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                created.append(path)
                stream.write(text)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def _fetch(args) -> int:
    """Live tenant in, one output document out (D-092). The bundle is fetched, then normalized by the
    same pipeline as ``normalize``; nothing is written unless the whole document was built. Output
    goes to the Git-ignored ``live_data/`` by default; the raw bundle only with --save-bundle."""
    def progress(line: str) -> None:
        print(line, file=sys.stderr, flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        provider = live_client.TENANTS[args.tenant]
        output = args.output or Path(LIVE_DIR) / f"{provider}-{stamp}.json"
        bundle_path = output.with_name(output.stem + ".bundle.json")
        for path in (output, bundle_path) if args.save_bundle else (output,):
            if path.exists():
                raise FileExistsError(f"{path} exists; refusing to overwrite")
        plan = import_module(PLANS[provider], "normalization.live")
        session = live_client.Session(args.tenant, live_client.api_key(), transport=live_client.urllib_transport,
                                      rate_limit=getattr(plan, "RATE_LIMIT", None))
        progress(f"signed in to {args.tenant}")
        window = (args.pay_from, args.pay_to) if args.pay_from else None
        fetched = fetch_tenant(session, args.as_of, args.company, window, args.workers, progress=progress)
        progress("normalizing")
        document = build_document(normalize_bundle(fetched.bundle), f"live:{args.tenant}", args.show_sensitive)
        document["run"]["fetch"] = fetched.report
        text = document_text(document)
        files = [(output, text)]
        if args.save_bundle:
            files.append((bundle_path, bundle_text(fetched.bundle, fetched.report)))
        write_new(files)
        if args.save_bundle:
            progress(f"raw bundle: {bundle_path} (personal data, keep out of Git)")
    except (live_client.FetchError, OSError, ValueError) as exc:
        print(f"error: {exc}; nothing written", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted; nothing written", file=sys.stderr)
        return 1
    except Exception as exc:  # an adapter fault: a clean failure, never a partial file (D-089)
        print(f"error: normalization failed ({type(exc).__name__}: {exc}); nothing written", file=sys.stderr)
        return 1
    report = fetched.report
    print(f"output: {output} ({', '.join(f'{name} {count}' for name, count in document['run']['counts'].items())})", file=sys.stderr)
    print(f"calls: {report['calls']} in {report['seconds']} s, statuses {report['statuses']}, sign-ins {report['sign_ins']}", file=sys.stderr)
    for route, count in report["unanswered"].items():
        print(f"unanswered after retries: {route} x{count}", file=sys.stderr)
    stopped = [window for window in report["pay_windows"].values() if str(window["basis"]).startswith("search stopped")]
    if stopped:
        print(f"pay window search stopped on an error for {len(stopped)} companies (run.fetch.pay_windows)", file=sys.stderr)
    # Counts only: the entries name ids, which stay in the output file (D-092).
    print(f"responses set aside: {len(document['run']['unusable_responses'])} (run.unusable_responses)", file=sys.stderr)
    print(f"link problems: {len(document['run']['link_problems'])} (run.link_problems)", file=sys.stderr)
    if args.show_sensitive:
        print("warning: sensitive values are shown in full (--show-sensitive)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

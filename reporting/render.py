from jinja2 import Environment, FileSystemLoader, select_autoescape
import os


def generate_report(output: dict, template_name: str = "report_template.html", out_path: str = None):
    base_dir = os.path.dirname(__file__)
    env = Environment(
        loader=FileSystemLoader(base_dir),
        autoescape=select_autoescape(["html", "xml"])
    )

    template = env.get_template(template_name)
    html = template.render(**output)

    if out_path is None:
        out_path = os.path.join(os.getcwd(), "report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

import io
import os
import base64
import qrcode
from django.conf import settings
from django.template.loader import render_to_string
from weasyprint import HTML, CSS


def generate_qr_code(data: str) -> bytes:
    """Generate QR code image as PNG bytes."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer.getvalue()


def image_to_base64(path: str) -> str:
    """Convert image file to base64 string."""
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        return ""


def generate_ticket_pdf(participant, olympiad=None) -> bytes:
    """Generate PDF ticket with QR code for participant using WeasyPrint."""
    from .models import OlympiadSettings, Order, Subject

    # Generate QR code
    qr_bytes = generate_qr_code(str(participant.id))
    qr_code_base64 = base64.b64encode(qr_bytes).decode("utf-8")

    # Get logo paths
    img_dir = settings.BASE_DIR / "apps" / "public" / "static" / "public" / "img"
    logo1_base64 = image_to_base64(str(img_dir / "logo-1.png"))
    logo2_base64 = image_to_base64(str(img_dir / "data.png"))

    # Get font paths
    fonts_dir = settings.BASE_DIR / "apps" / "public" / "static" / "public" / "fonts"
    font_path = str(fonts_dir / "DejaVuSans.ttf")
    font_bold_path = str(fonts_dir / "DejaVuSans-Bold.ttf")

    # Get olympiad settings
    if olympiad is None:
        olympiad = OlympiadSettings.get_active()

    # Get purchased subjects
    purchased_subjects = []
    if olympiad:
        purchased_subjects = Subject.objects.filter(
            orders__participant=participant,
            orders__olympiad=olympiad,
            orders__status='paid'
        ).distinct()


    # Prepare context for template
    context = {
        "participant": participant,
        "event_name": "Bond - Viloyat bosqichi",
        "qr_code_base64": qr_code_base64,
        "logo1_base64": logo1_base64,
        "logo2_base64": logo2_base64,
        "font_path": font_path,
        "font_bold_path": font_bold_path,
        "olympiad": olympiad,
        "purchased_subjects": purchased_subjects,
    }

    # Render HTML template
    html_string = render_to_string("public/ticket_template.html", context)

    # Generate PDF with WeasyPrint
    html = HTML(string=html_string, base_url=str(settings.BASE_DIR))
    pdf_bytes = html.write_pdf()

    return pdf_bytes

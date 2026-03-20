from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime
import random
import mercadopago
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'skywater_db')]

# Mercado Pago configuration
MERCADO_PAGO_ACCESS_TOKEN = os.environ.get('MERCADO_PAGO_ACCESS_TOKEN', '')
MERCADO_PAGO_PUBLIC_KEY = os.environ.get('MERCADO_PAGO_PUBLIC_KEY', '')

# Initialize Mercado Pago SDK
mp_sdk = None
if MERCADO_PAGO_ACCESS_TOKEN:
    mp_sdk = mercadopago.SDK(MERCADO_PAGO_ACCESS_TOKEN)

# Create the main app
app = FastAPI(title="SKY WATER API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# ============== LEGAL PAGES HTML TEMPLATE ==============

def get_legal_page_html(title: str, content: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} - Sky Water</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                background: linear-gradient(135deg, #000A1A 0%, #001F3F 100%);
                color: #FFFFFF;
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
                background: rgba(0, 206, 209, 0.05);
                border: 1px solid rgba(0, 206, 209, 0.2);
                border-radius: 16px;
                padding: 40px;
            }}
            .logo {{
                text-align: center;
                margin-bottom: 30px;
            }}
            .logo h1 {{
                color: #00FFFF;
                font-size: 2.5em;
                text-shadow: 0 0 20px rgba(0, 255, 255, 0.5);
            }}
            .logo p {{
                color: #40E0D0;
                margin-top: 5px;
            }}
            h2 {{
                color: #00CED1;
                font-size: 1.8em;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 1px solid rgba(0, 206, 209, 0.3);
            }}
            h3 {{
                color: #40E0D0;
                font-size: 1.3em;
                margin: 25px 0 15px 0;
            }}
            p {{
                line-height: 1.8;
                margin-bottom: 15px;
                color: #E0E0E0;
            }}
            ul {{
                margin: 15px 0 15px 30px;
            }}
            li {{
                line-height: 1.8;
                margin-bottom: 8px;
                color: #E0E0E0;
            }}
            .highlight {{
                background: rgba(0, 206, 209, 0.1);
                border-left: 4px solid #00CED1;
                padding: 15px 20px;
                margin: 20px 0;
                border-radius: 0 8px 8px 0;
            }}
            .warning {{
                background: rgba(255, 215, 0, 0.1);
                border-left: 4px solid #FFD700;
                padding: 15px 20px;
                margin: 20px 0;
                border-radius: 0 8px 8px 0;
            }}
            .warning p {{
                color: #FFD700;
            }}
            .footer {{
                text-align: center;
                margin-top: 40px;
                padding-top: 20px;
                border-top: 1px solid rgba(0, 206, 209, 0.2);
                color: #888;
            }}
            .date {{
                color: #00CED1;
                font-weight: bold;
            }}
            a {{
                color: #00FFFF;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">
                <h1>🌊 SKY WATER</h1>
                <p>Sanación Energética desde el Cielo</p>
            </div>
            {content}
            <div class="footer">
                <p>© 2025 Sky Water. Todos los derechos reservados.</p>
                <p><a href="/api/legal/privacy">Política de Privacidad</a> | <a href="/api/legal/terms">Términos y Condiciones</a> | <a href="/api/legal/disclaimer">Descargo de Responsabilidad</a></p>
            </div>
        </div>
    </body>
    </html>
    """

# ============== LEGAL ROUTES ==============

@api_router.get("/legal/privacy", response_class=HTMLResponse)
async def privacy_policy():
    """Privacy Policy page"""
    content = """
    <h2>Política de Privacidad</h2>
    <p class="date">Última actualización: Marzo 2025</p>
    
    <h3>1. Introducción</h3>
    <p>Sky Water ("nosotros", "nuestro" o "la aplicación") se compromete a proteger la privacidad de nuestros usuarios. Esta Política de Privacidad describe cómo recopilamos, usamos, almacenamos y protegemos su información personal cuando utiliza nuestra aplicación móvil y servicios relacionados.</p>
    
    <h3>2. Información que Recopilamos</h3>
    <p>Recopilamos la siguiente información personal cuando utiliza nuestros servicios:</p>
    <ul>
        <li><strong>Información de identificación:</strong> Nombre completo (nombres y apellidos)</li>
        <li><strong>Información de contacto:</strong> Dirección de correo electrónico</li>
        <li><strong>Información de ubicación:</strong> País, estado/provincia, ciudad, dirección completa y código postal</li>
        <li><strong>Información personal:</strong> Fecha de nacimiento</li>
        <li><strong>Información de salud:</strong> Descripción de síntomas y padecimientos proporcionados voluntariamente por el usuario</li>
        <li><strong>Información de pago:</strong> Datos de transacciones (no almacenamos datos completos de tarjetas de crédito)</li>
    </ul>
    
    <h3>3. Cómo Utilizamos su Información</h3>
    <p>Utilizamos su información personal para:</p>
    <ul>
        <li>Proporcionar y personalizar nuestros servicios de sanación energética</li>
        <li>Procesar pagos y transacciones</li>
        <li>Comunicarnos con usted sobre su servicio</li>
        <li>Enviar confirmaciones de órdenes y actualizaciones</li>
        <li>Mejorar nuestros servicios y experiencia del usuario</li>
        <li>Cumplir con obligaciones legales</li>
    </ul>
    
    <h3>4. Protección de Datos de Salud</h3>
    <div class="highlight">
        <p>La información de salud que usted proporciona (síntomas, padecimientos) se considera información sensible. Esta información:</p>
        <ul>
            <li>Se utiliza exclusivamente para los fines del servicio solicitado</li>
            <li>No se comparte con terceros sin su consentimiento</li>
            <li>Se almacena de forma segura con encriptación</li>
            <li>Puede ser eliminada a solicitud del usuario</li>
        </ul>
    </div>
    
    <h3>5. Compartir Información</h3>
    <p>No vendemos, alquilamos ni compartimos su información personal con terceros, excepto:</p>
    <ul>
        <li>Procesadores de pago (Mercado Pago) para completar transacciones</li>
        <li>Cuando sea requerido por ley o autoridades competentes</li>
        <li>Para proteger nuestros derechos legales</li>
    </ul>
    
    <h3>6. Seguridad de Datos</h3>
    <p>Implementamos medidas de seguridad técnicas y organizativas para proteger su información, incluyendo:</p>
    <ul>
        <li>Encriptación de datos en tránsito y en reposo</li>
        <li>Acceso restringido a información personal</li>
        <li>Monitoreo regular de seguridad</li>
        <li>Servidores seguros</li>
    </ul>
    
    <h3>7. Sus Derechos</h3>
    <p>Usted tiene derecho a:</p>
    <ul>
        <li>Acceder a su información personal</li>
        <li>Rectificar datos inexactos</li>
        <li>Solicitar la eliminación de sus datos</li>
        <li>Oponerse al procesamiento de sus datos</li>
        <li>Retirar su consentimiento en cualquier momento</li>
    </ul>
    
    <h3>8. Retención de Datos</h3>
    <p>Conservamos su información personal mientras sea necesario para proporcionar nuestros servicios y cumplir con obligaciones legales. Puede solicitar la eliminación de sus datos contactándonos.</p>
    
    <h3>9. Menores de Edad</h3>
    <p>Nuestros servicios no están dirigidos a menores de 18 años. No recopilamos intencionalmente información de menores.</p>
    
    <h3>10. Cambios a esta Política</h3>
    <p>Podemos actualizar esta política periódicamente. Le notificaremos cambios significativos a través de la aplicación o por correo electrónico.</p>
    
    <h3>11. Contacto</h3>
    <p>Para preguntas sobre esta política o para ejercer sus derechos, contáctenos en:</p>
    <p><strong>Email:</strong> privacy@skywater.app</p>
    """
    return get_legal_page_html("Política de Privacidad", content)

@api_router.get("/legal/terms", response_class=HTMLResponse)
async def terms_of_service():
    """Terms of Service page"""
    content = """
    <h2>Términos y Condiciones de Uso</h2>
    <p class="date">Última actualización: Marzo 2025</p>
    
    <h3>1. Aceptación de los Términos</h3>
    <p>Al acceder y utilizar la aplicación Sky Water y sus servicios, usted acepta estar sujeto a estos Términos y Condiciones. Si no está de acuerdo con alguna parte de estos términos, no debe utilizar nuestros servicios.</p>
    
    <h3>2. Descripción del Servicio</h3>
    <p>Sky Water ofrece servicios de sanación energética a distancia en tiempo real. El servicio consiste en:</p>
    <ul>
        <li>7 niveles de tratamiento energético</li>
        <li>Conexión energética establecida después del procesamiento del pago</li>
        <li>Servicios basados en principios de energía vibracional</li>
    </ul>
    
    <div class="warning">
        <p><strong>⚠️ IMPORTANTE:</strong> Sky Water es un servicio de sanación energética complementaria y NO constituye atención médica. No sustituye el diagnóstico, tratamiento o consejo médico profesional.</p>
    </div>
    
    <h3>3. Requisitos del Usuario</h3>
    <p>Para utilizar nuestros servicios, usted debe:</p>
    <ul>
        <li>Ser mayor de 18 años</li>
        <li>Proporcionar información veraz y precisa</li>
        <li>Tener capacidad legal para celebrar contratos</li>
        <li>No utilizar el servicio para fines ilegales</li>
    </ul>
    
    <h3>4. Veracidad de la Información</h3>
    <div class="highlight">
        <p>El funcionamiento del servicio depende de la exactitud de la información proporcionada. Usted garantiza que:</p>
        <ul>
            <li>Toda la información personal es verdadera y actual</li>
            <li>La descripción de síntomas es precisa y completa</li>
            <li>Comprende que información falsa invalida el proceso</li>
        </ul>
    </div>
    
    <h3>5. Precios y Pagos</h3>
    <p>Los precios de nuestros servicios están expresados en dólares estadounidenses (USD). Al realizar un pago:</p>
    <ul>
        <li>Acepta el precio del nivel seleccionado</li>
        <li>Autoriza el cargo a su método de pago</li>
        <li>Reconoce que los pagos son anticipados</li>
    </ul>
    
    <h3>6. Política de No Reembolso</h3>
    <div class="warning">
        <p><strong>TODOS LOS PAGOS SON FINALES Y NO REEMBOLSABLES.</strong></p>
        <p>Una vez procesado el pago, el servicio de sanación energética se activa inmediatamente. No se realizan reembolsos bajo ninguna circunstancia.</p>
    </div>
    
    <h3>7. Limitación de Responsabilidad</h3>
    <p>Sky Water no se hace responsable de:</p>
    <ul>
        <li>Resultados específicos o garantizados del servicio</li>
        <li>Decisiones médicas tomadas por el usuario</li>
        <li>Daños directos, indirectos o consecuentes</li>
        <li>Interrupciones técnicas del servicio</li>
        <li>Información incorrecta proporcionada por el usuario</li>
    </ul>
    
    <h3>8. Propiedad Intelectual</h3>
    <p>Todo el contenido de Sky Water, incluyendo logos, textos, gráficos y software, está protegido por derechos de autor y otras leyes de propiedad intelectual.</p>
    
    <h3>9. Uso Aceptable</h3>
    <p>Usted se compromete a no:</p>
    <ul>
        <li>Usar el servicio para fines fraudulentos</li>
        <li>Intentar acceder a sistemas no autorizados</li>
        <li>Distribuir malware o código dañino</li>
        <li>Violar derechos de terceros</li>
    </ul>
    
    <h3>10. Terminación</h3>
    <p>Nos reservamos el derecho de suspender o terminar su acceso al servicio si viola estos términos, sin previo aviso y sin derecho a reembolso.</p>
    
    <h3>11. Modificaciones</h3>
    <p>Podemos modificar estos términos en cualquier momento. El uso continuado del servicio después de cambios constituye aceptación de los nuevos términos.</p>
    
    <h3>12. Ley Aplicable</h3>
    <p>Estos términos se rigen por las leyes aplicables en la jurisdicción donde opera Sky Water. Cualquier disputa será resuelta en los tribunales competentes de dicha jurisdicción.</p>
    
    <h3>13. Contacto</h3>
    <p>Para consultas sobre estos términos:</p>
    <p><strong>Email:</strong> legal@skywater.app</p>
    """
    return get_legal_page_html("Términos y Condiciones", content)

@api_router.get("/legal/disclaimer", response_class=HTMLResponse)
async def disclaimer():
    """Medical Disclaimer page"""
    content = """
    <h2>Descargo de Responsabilidad Médica</h2>
    <p class="date">Última actualización: Marzo 2025</p>
    
    <div class="warning">
        <p><strong>⚠️ ADVERTENCIA IMPORTANTE - LEA CUIDADOSAMENTE</strong></p>
        <p>Este documento contiene información crucial sobre la naturaleza de los servicios de Sky Water y sus limitaciones.</p>
    </div>
    
    <h3>1. Naturaleza del Servicio</h3>
    <p>Sky Water es un servicio de <strong>sanación energética complementaria</strong>. Nuestros servicios:</p>
    <ul>
        <li>NO son tratamientos médicos</li>
        <li>NO son servicios de atención sanitaria</li>
        <li>NO son diagnósticos médicos</li>
        <li>NO son terapias físicas o psicológicas reguladas</li>
        <li>NO sustituyen la atención médica profesional</li>
    </ul>
    
    <h3>2. No Somos Profesionales de la Salud</h3>
    <div class="highlight">
        <p>Sky Water y su personal <strong>NO son</strong>:</p>
        <ul>
            <li>Médicos licenciados</li>
            <li>Profesionales de la salud certificados</li>
            <li>Terapeutas regulados</li>
            <li>Practicantes de medicina</li>
        </ul>
        <p>No ofrecemos diagnósticos, tratamientos médicos ni consejos de salud profesionales.</p>
    </div>
    
    <h3>3. Consulte a su Médico</h3>
    <p><strong>SIEMPRE</strong> consulte con un profesional de la salud calificado:</p>
    <ul>
        <li>Antes de tomar decisiones sobre su salud</li>
        <li>Si experimenta síntomas de enfermedad</li>
        <li>Antes de suspender cualquier tratamiento médico</li>
        <li>Si tiene condiciones médicas preexistentes</li>
        <li>Si está embarazada o en período de lactancia</li>
    </ul>
    
    <h3>4. No Suspenda Tratamientos Médicos</h3>
    <div class="warning">
        <p><strong>NUNCA suspenda, modifique o ignore tratamientos médicos prescritos</strong> por un profesional de la salud debido a los servicios de Sky Water.</p>
    </div>
    
    <h3>5. Sin Garantías de Resultados</h3>
    <p>Sky Water:</p>
    <ul>
        <li>NO garantiza resultados específicos</li>
        <li>NO garantiza curas o sanaciones</li>
        <li>NO garantiza tiempos de respuesta</li>
        <li>NO garantiza mejoras en condiciones de salud</li>
    </ul>
    <p>Los resultados, si los hubiere, varían de persona a persona y no pueden predecirse ni garantizarse.</p>
    
    <h3>6. Uso Bajo su Propio Riesgo</h3>
    <p>Al utilizar los servicios de Sky Water, usted:</p>
    <ul>
        <li>Acepta que lo hace bajo su propio riesgo</li>
        <li>Asume toda la responsabilidad de su salud</li>
        <li>Entiende la naturaleza no médica del servicio</li>
        <li>Renuncia a reclamaciones contra Sky Water</li>
    </ul>
    
    <h3>7. Emergencias Médicas</h3>
    <div class="warning">
        <p><strong>En caso de emergencia médica, llame inmediatamente a los servicios de emergencia de su localidad.</strong></p>
        <p>Sky Water NO es un servicio de emergencias y NO puede proporcionar atención médica urgente.</p>
    </div>
    
    <h3>8. Información de Salud Proporcionada</h3>
    <p>La información de salud (síntomas, padecimientos) que usted proporciona:</p>
    <ul>
        <li>Se utiliza únicamente para fines del servicio energético</li>
        <li>NO constituye un historial médico profesional</li>
        <li>NO será utilizada para diagnóstico médico</li>
        <li>NO reemplaza la evaluación médica profesional</li>
    </ul>
    
    <h3>9. Exención Total de Responsabilidad</h3>
    <div class="highlight">
        <p>Sky Water, sus propietarios, operadores, empleados y asociados quedan <strong>COMPLETAMENTE EXENTOS</strong> de cualquier responsabilidad por:</p>
        <ul>
            <li>Daños físicos, emocionales o psicológicos</li>
            <li>Pérdidas económicas</li>
            <li>Empeoramiento de condiciones de salud</li>
            <li>Efectos adversos de cualquier naturaleza</li>
            <li>Decisiones médicas del usuario</li>
            <li>Cualquier consecuencia del uso del servicio</li>
        </ul>
    </div>
    
    <h3>10. Declaración del Usuario</h3>
    <p>Al utilizar Sky Water, usted declara y garantiza que:</p>
    <ul>
        <li>Ha leído y comprendido este descargo de responsabilidad</li>
        <li>Entiende que NO es un servicio médico</li>
        <li>No suspenderá tratamientos médicos</li>
        <li>Consultará profesionales de salud para sus condiciones médicas</li>
        <li>Acepta los servicios bajo su exclusiva responsabilidad</li>
        <li>Renuncia a cualquier reclamación contra Sky Water</li>
    </ul>
    
    <h3>11. Base del Servicio</h3>
    <p>Los servicios de Sky Water se basan en:</p>
    <ul>
        <li>Principios de energía vibracional</li>
        <li>Conceptos de sanación energética complementaria</li>
        <li>Prácticas de bienestar alternativo</li>
    </ul>
    <p>Estos conceptos pueden no ser reconocidos por la medicina convencional y no cuentan con validación científica en el sentido médico tradicional.</p>
    
    <h3>12. Contacto</h3>
    <p>Para preguntas sobre este descargo:</p>
    <p><strong>Email:</strong> legal@skywater.app</p>
    """
    return get_legal_page_html("Descargo de Responsabilidad Médica", content)

@api_router.get("/legal/consent", response_class=HTMLResponse)
async def informed_consent():
    """Informed Consent page"""
    content = """
    <h2>Consentimiento Informado</h2>
    <p class="date">Última actualización: Marzo 2025</p>
    
    <h3>Declaración de Consentimiento</h3>
    <p>Antes de utilizar los servicios de Sky Water, es fundamental que lea, comprenda y acepte la siguiente información:</p>
    
    <h3>1. Entiendo la Naturaleza del Servicio</h3>
    <div class="highlight">
        <p>Yo, el usuario, declaro que <strong>ENTIENDO Y ACEPTO</strong> que:</p>
        <ul>
            <li>Sky Water ofrece servicios de sanación energética complementaria</li>
            <li>NO es un servicio médico ni de atención sanitaria</li>
            <li>NO sustituye diagnóstico o tratamiento médico profesional</li>
            <li>Los resultados no están garantizados y varían según cada persona</li>
        </ul>
    </div>
    
    <h3>2. Declaro Voluntariamente</h3>
    <p>Por medio del presente, declaro de manera <strong>libre, voluntaria e informada</strong> que:</p>
    <ul>
        <li>Soy mayor de 18 años con plena capacidad legal</li>
        <li>He leído completamente la Política de Privacidad</li>
        <li>He leído completamente los Términos y Condiciones</li>
        <li>He leído completamente el Descargo de Responsabilidad Médica</li>
        <li>Comprendo todos los documentos mencionados</li>
    </ul>
    
    <h3>3. Sobre Mi Información de Salud</h3>
    <p>Respecto a la información de salud que proporciono:</p>
    <ul>
        <li>La información es <strong>veraz, precisa y completa</strong></li>
        <li>Entiendo que información falsa invalida el servicio</li>
        <li>Autorizo su uso para los fines del servicio energético</li>
        <li>Comprendo que NO se usará para diagnóstico médico</li>
    </ul>
    
    <h3>4. Sobre Mi Salud y Tratamientos</h3>
    <div class="warning">
        <p><strong>DECLARO QUE:</strong></p>
        <ul>
            <li>NO suspenderé tratamientos médicos por usar Sky Water</li>
            <li>Consultaré profesionales de salud para mis condiciones médicas</li>
            <li>Entiendo que debo buscar atención médica para problemas de salud</li>
            <li>En emergencias, contactaré servicios médicos de emergencia</li>
        </ul>
    </div>
    
    <h3>5. Asumo la Responsabilidad</h3>
    <p>Declaro que:</p>
    <ul>
        <li>Utilizo este servicio bajo mi <strong>exclusiva responsabilidad</strong></li>
        <li>Asumo todos los riesgos asociados</li>
        <li>Mantengo toda la responsabilidad sobre mi salud y bienestar</li>
        <li>Eximo a Sky Water de responsabilidad por los resultados</li>
    </ul>
    
    <h3>6. Sobre el Pago</h3>
    <p>Entiendo y acepto que:</p>
    <ul>
        <li>Todos los pagos son <strong>anticipados</strong></li>
        <li>Todos los pagos son <strong>finales y no reembolsables</strong></li>
        <li>El servicio se activa inmediatamente después del pago</li>
        <li>No hay garantía de resultados específicos</li>
    </ul>
    
    <h3>7. Consentimiento de Datos</h3>
    <p>Autorizo a Sky Water a:</p>
    <ul>
        <li>Recopilar la información personal que proporciono</li>
        <li>Almacenar mis datos de forma segura</li>
        <li>Utilizar mi información para prestar el servicio</li>
        <li>Contactarme sobre mi servicio vía email</li>
    </ul>
    
    <h3>8. Declaración Final</h3>
    <div class="highlight">
        <p><strong>AL UTILIZAR LOS SERVICIOS DE SKY WATER, CONFIRMO QUE:</strong></p>
        <ul>
            <li>He leído todos los documentos legales en su totalidad</li>
            <li>Comprendo la naturaleza del servicio de sanación energética</li>
            <li>Acepto todos los términos, condiciones y limitaciones</li>
            <li>Proporciono mi consentimiento de manera libre e informada</li>
            <li>Renuncio a reclamaciones contra Sky Water</li>
        </ul>
    </div>
    
    <h3>9. Revocación del Consentimiento</h3>
    <p>Puedo revocar mi consentimiento para el procesamiento futuro de mis datos contactando a:</p>
    <p><strong>Email:</strong> privacy@skywater.app</p>
    <p>Nota: La revocación no afecta la legalidad del procesamiento previo ni el derecho a pagos ya realizados.</p>
    """
    return get_legal_page_html("Consentimiento Informado", content)

# ============== MODELS ==============

class Product(BaseModel):
    id: str
    level: int
    name: str
    icon: str
    price: float
    indication: str
    examples: str
    description: str
    badge: Optional[str] = None

class PatientData(BaseModel):
    first_name: str
    second_name: str
    first_lastname: str
    second_lastname: str
    country: str
    state: str
    city: str
    address: str
    postal_code: str
    birth_date: str
    symptoms: str
    email: str

class OrderCreate(BaseModel):
    product_id: str
    patient_data: PatientData
    terms_accepted: bool

class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_number: str = Field(default_factory=lambda: f"SKYWATER-{random.randint(10000, 99999)}")
    product_id: str
    product_name: str
    product_price: float
    patient_data: PatientData
    terms_accepted: bool
    payment_method: Optional[str] = None
    payment_status: str = "pending"
    mercadopago_preference_id: Optional[str] = None
    mercadopago_payment_id: Optional[str] = None
    transaction_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    paid_at: Optional[datetime] = None

class PaymentUpdate(BaseModel):
    payment_method: str
    transaction_hash: Optional[str] = None

class MercadoPagoPreference(BaseModel):
    order_id: str

class Testimonial(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    rating: int
    location: str
    level: int
    level_name: str
    text: str
    date: str
    verified: bool = True

# ============== PRODUCTS DATA ==============

PRODUCTS = [
    Product(
        id="level-1",
        level=1,
        name="Revisión Pre-Tratamiento",
        icon="stethoscope",
        price=4.99,
        indication="Análisis Energético Diagnóstico",
        examples="Evaluación completa de tu estado energético, identificación de bloqueos, análisis de condiciones de salud",
        description="Estudio completo de tus condiciones de salud donde identificamos la condición más importante que debes atender, incluyendo el origen del problema. Recibirás un diagnóstico energético personalizado que guiará tu proceso de sanación.",
        badge="Primer Paso Esencial"
    ),
    Product(
        id="level-2",
        level=2,
        name="Ligero Rocío de Sky Water",
        icon="cloud-rain",
        price=19.99,
        indication="Prueba de Efectividad Energética",
        examples="Dolor leve de cabeza, molestia muscular pasajera, incomodidad articular menor, tensión cervical leve",
        description="¿Eres nuevo o escéptico? Este nivel está diseñado para ti. Una micro-dosis de energía sanadora que te permitirá experimentar y comprobar por ti mismo el poder de Sky Water. Carga energética inicial calibrada para demostrar efectividad tangible en molestias menores.",
        badge="Para Nuevos y Escépticos"
    ),
    Product(
        id="level-3",
        level=3,
        name="Una Gota de Sky Water",
        icon="droplet",
        price=49.99,
        indication="Sanación para Creyentes",
        examples="Dolor leve persistente, malestar menor recurrente, tensión ligera acumulada",
        description="Ya experimentaste el poder de Sky Water y CREES. Este nivel activa una carga energética significativamente mayor. Diseñado para quienes confían plenamente en el proceso y están listos para recibir una sanación más profunda.",
        badge="Carga Energética Potenciada"
    ),
    Product(
        id="level-4",
        level=4,
        name="Un Shot de Sky Water",
        icon="glass-water",
        price=97,
        indication="Curación simple",
        examples="Dolor fuerte, malestar agudo, incomodidad intensa",
        description="Para dolores más intensos que necesitan una dosis concentrada de sanación. Sesión completa de 60 minutos."
    ),
    Product(
        id="level-5",
        level=5,
        name="Una Copa de Sky Water",
        icon="wine-glass",
        price=197,
        indication="Padecimiento crónico no grave",
        examples="Dolor persistente, molestias recurrentes, padecimientos de larga duración",
        description="Paquete de 3 sesiones perfecto para condiciones que llevan tiempo contigo y necesitan atención profunda",
        badge="Más Popular"
    ),
    Product(
        id="level-6",
        level=6,
        name="500ml de Sky Water",
        icon="bottle-water",
        price=397,
        indication="Padecimiento agudo moderado",
        examples="Virus respiratorios agresivos, infecciones, condiciones agudas moderadas",
        description="Paquete de 6 sesiones. Sanación potente para condiciones agudas que afectan tu bienestar actual"
    ),
    Product(
        id="level-7",
        level=7,
        name="1 Litro de Sky Water",
        icon="bottle-droplet",
        price=697,
        indication="Padecimiento moderado crónico",
        examples="Cefaleas constantes, migrañas recurrentes, dolores crónicos moderados",
        description="Programa trimestral de 12 sesiones para condiciones crónicas que requieren intervención energética sustancial"
    ),
    Product(
        id="level-8",
        level=8,
        name="2 Litros de Sky Water",
        icon="jug",
        price=997,
        indication="Padecimiento grave crónico",
        examples="Dolores de espalda por desplazamiento vertebral, hernias discales, padecimientos graves de larga data",
        description="Programa semestral de 24 sesiones. Sanación profunda para condiciones graves y complejas"
    ),
    Product(
        id="level-9",
        level=9,
        name="Una Fuente de Sky Water",
        icon="fountain",
        price=1997,
        indication="Curación de múltiples padecimientos simultáneos",
        examples="Combinación de varios padecimientos (leves, moderados, graves, agudos, crónicos)",
        description="Programa anual con sesiones ilimitadas. La experiencia completa de Sky Water. Sanación integral para múltiples condiciones de manera simultánea",
        badge="Transformación Total"
    ),
]

USDT_WALLET = "0x169e4e6b0622853c501b78b24c359116416857bd"

# ============== API ROUTES ==============

@api_router.get("/")
async def root():
    return {"message": "SKY WATER API - Sanación Energética en Tiempo Real"}

@api_router.get("/products", response_model=List[Product])
async def get_products():
    return PRODUCTS

@api_router.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str):
    for product in PRODUCTS:
        if product.id == product_id:
            return product
    raise HTTPException(status_code=404, detail="Product not found")

@api_router.post("/orders", response_model=Order)
async def create_order(order_data: OrderCreate):
    if not order_data.terms_accepted:
        raise HTTPException(status_code=400, detail="Terms must be accepted")
    
    product = None
    for p in PRODUCTS:
        if p.id == order_data.product_id:
            product = p
            break
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    order = Order(
        product_id=product.id,
        product_name=product.name,
        product_price=product.price,
        patient_data=order_data.patient_data,
        terms_accepted=order_data.terms_accepted
    )
    
    await db.orders.insert_one(order.dict())
    return order

@api_router.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: str):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return Order(**order)

@api_router.patch("/orders/{order_id}/payment")
async def update_payment(order_id: str, payment: PaymentUpdate):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    update_data = {
        "payment_method": payment.payment_method,
        "payment_status": "processing" if payment.payment_method == "usdt" else "pending",
    }
    
    if payment.transaction_hash:
        update_data["transaction_hash"] = payment.transaction_hash
        update_data["payment_status"] = "completed"
        update_data["paid_at"] = datetime.utcnow()
    
    await db.orders.update_one({"id": order_id}, {"$set": update_data})
    updated_order = await db.orders.find_one({"id": order_id})
    return Order(**updated_order)

@api_router.get("/wallet")
async def get_wallet():
    return {
        "wallet_address": USDT_WALLET,
        "network": "ERC20",
        "currency": "USDT"
    }

# ============== MERCADO PAGO ROUTES ==============

@api_router.get("/mercadopago/config")
async def get_mercadopago_config():
    return {
        "public_key": MERCADO_PAGO_PUBLIC_KEY,
        "configured": bool(MERCADO_PAGO_ACCESS_TOKEN)
    }

@api_router.post("/mercadopago/preference")
async def create_mercadopago_preference(data: MercadoPagoPreference):
    if not mp_sdk:
        raise HTTPException(status_code=500, detail="Mercado Pago not configured")
    
    order = await db.orders.find_one({"id": data.order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order_obj = Order(**order)
    
    preference_data = {
        "items": [
            {
                "id": order_obj.product_id,
                "title": f"Sky Water - {order_obj.product_name}",
                "description": f"Sanación Energética Nivel {order_obj.product_id.split('-')[1]}",
                "quantity": 1,
                "currency_id": "MXN",
                "unit_price": order_obj.product_price * 17.5
            }
        ],
        "payer": {
            "email": order_obj.patient_data.email,
            "name": f"{order_obj.patient_data.first_name} {order_obj.patient_data.first_lastname}",
        },
        "external_reference": order_obj.id,
        "back_urls": {
            "success": f"https://sacred-wavelength.preview.emergentagent.com/checkout/confirmation?order_id={order_obj.id}&status=approved",
            "failure": f"https://sacred-wavelength.preview.emergentagent.com/checkout/payment?order_id={order_obj.id}&status=failure",
            "pending": f"https://sacred-wavelength.preview.emergentagent.com/checkout/payment?order_id={order_obj.id}&status=pending"
        },
        "auto_return": "approved",
        "notification_url": "https://sacred-wavelength.preview.emergentagent.com/api/mercadopago/webhook",
        "statement_descriptor": "SKY WATER",
    }
    
    try:
        preference_response = mp_sdk.preference().create(preference_data)
        
        if preference_response["status"] == 201:
            preference = preference_response["response"]
            
            await db.orders.update_one(
                {"id": order_obj.id},
                {"$set": {
                    "mercadopago_preference_id": preference["id"],
                    "payment_method": "mercadopago"
                }}
            )
            
            return {
                "preference_id": preference["id"],
                "init_point": preference["init_point"],
                "sandbox_init_point": preference.get("sandbox_init_point", preference["init_point"]),
                "order_id": order_obj.id
            }
        else:
            raise HTTPException(status_code=400, detail="Error creating preference")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating payment: {str(e)}")

@api_router.post("/mercadopago/webhook")
async def mercadopago_webhook(request: Request):
    try:
        payload = await request.json()
        
        if payload.get("type") == "payment":
            payment_id = payload.get("data", {}).get("id")
            
            if payment_id and mp_sdk:
                payment_response = mp_sdk.payment().get(payment_id)
                
                if payment_response["status"] == 200:
                    payment = payment_response["response"]
                    external_reference = payment.get("external_reference")
                    payment_status = payment.get("status")
                    
                    if external_reference:
                        status_map = {
                            "approved": "completed",
                            "pending": "processing",
                            "in_process": "processing",
                            "rejected": "failed",
                            "cancelled": "cancelled",
                            "refunded": "refunded"
                        }
                        
                        update_data = {
                            "mercadopago_payment_id": str(payment_id),
                            "payment_status": status_map.get(payment_status, "pending")
                        }
                        
                        if payment_status == "approved":
                            update_data["paid_at"] = datetime.utcnow()
                        
                        await db.orders.update_one(
                            {"id": external_reference},
                            {"$set": update_data}
                        )
        
        return {"status": "received"}
    except Exception as e:
        return {"status": "received"}

@api_router.get("/mercadopago/payment-status/{order_id}")
async def get_payment_status(order_id: str):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return {
        "order_id": order_id,
        "payment_status": order.get("payment_status", "pending"),
        "payment_method": order.get("payment_method"),
        "mercadopago_payment_id": order.get("mercadopago_payment_id"),
        "paid_at": order.get("paid_at")
    }

# ============== TESTIMONIALS ROUTES ==============

@api_router.get("/testimonials", response_model=List[Testimonial])
async def get_testimonials(page: int = 1, limit: int = 12, level: Optional[int] = None):
    skip = (page - 1) * limit
    query = {}
    if level:
        query["level"] = level
    
    testimonials = await db.testimonials.find(query).skip(skip).limit(limit).to_list(limit)
    return [Testimonial(**t) for t in testimonials]

@api_router.get("/testimonials/count")
async def get_testimonials_count():
    count = await db.testimonials.count_documents({})
    return {"count": count}

@api_router.post("/testimonials/seed")
async def seed_testimonials():
    count = await db.testimonials.count_documents({})
    if count > 0:
        return {"message": f"Already have {count} testimonials", "seeded": False}
    
    sample_testimonials = generate_testimonials()
    await db.testimonials.insert_many([t.dict() for t in sample_testimonials])
    return {"message": f"Seeded {len(sample_testimonials)} testimonials", "seeded": True}

@api_router.post("/testimonials/reseed")
async def reseed_testimonials():
    await db.testimonials.delete_many({})
    sample_testimonials = generate_testimonials()
    await db.testimonials.insert_many([t.dict() for t in sample_testimonials])
    return {"message": f"Reseeded {len(sample_testimonials)} testimonials", "seeded": True}

def generate_testimonials():
    first_names_male = ["Carlos", "Miguel", "Juan", "Pedro", "Roberto", "Fernando", "Diego", "Andrés", "Ricardo", "Jorge"]
    first_names_female = ["María", "Sofía", "Laura", "Ana", "Carmen", "Isabel", "Patricia", "Lucía", "Elena", "Claudia"]
    last_initials = ["A", "B", "C", "D", "E", "F", "G", "H", "L", "M", "N", "O", "P", "R", "S", "T", "V"]
    
    locations = [
        "Ciudad de México, México", "Monterrey, México", "Guadalajara, México",
        "Madrid, España", "Barcelona, España", "Buenos Aires, Argentina",
        "Bogotá, Colombia", "Lima, Perú", "Santiago, Chile", "Miami, USA"
    ]
    
    level_names = {
        1: "Revisión Pre-Tratamiento",
        2: "Ligero Rocío de Sky Water",
        3: "Una Gota de Sky Water", 
        4: "Un Shot de Sky Water", 
        5: "Una Copa de Sky Water",
        6: "500ml de Sky Water", 
        7: "1 Litro de Sky Water", 
        8: "2 Litros de Sky Water",
        9: "Una Fuente de Sky Water"
    }
    
    testimonial_texts = {
        1: ["La revisión me ayudó a entender exactamente qué necesitaba sanar. Muy revelador.", "El diagnóstico energético fue preciso. Ahora sé por dónde empezar mi sanación.", "Por solo $4.99 obtuve claridad sobre mi condición. Excelente primer paso."],
        2: ["Tenía una molestia leve en el cuello por dormir mal. En unas horas se fue completamente.", "Un dolor de cabeza menor que no me dejaba concentrar. Desapareció al poco tiempo.", "Probé Sky Water por primera vez con una incomodidad muscular. Me convenció al instante."],
        3: ["Tenía un dolor de cabeza leve. Después de Sky Water, desapareció en horas. Increíble.", "Molestia menor en el hombro. Al día siguiente ya no sentía nada."],
        4: ["Dolor de muelas insoportable y a las 3 horas ya no sentía nada. Impresionante.", "Un dolor de espalda agudo. Sky Water lo resolvió en un día."],
        5: ["Llevaba 5 AÑOS con migrañas. Sky Water me devolvió mi vida.", "Mi artritis en las manos me impedía trabajar. Ahora puedo escribir sin dolor."],
        6: ["Un virus respiratorio me tenía muy mal. Sky Water me ayudó a recuperarme.", "Infección persistente que no cedía. Con Sky Water mejoré."],
        7: ["Migrañas que me incapacitaban 3 veces por semana. Ahora vivo normalmente.", "Dolores crónicos de una década. Por fin encontré alivio."],
        8: ["Hernia discal L4-L5. Sky Water me salvó de la cirugía.", "Dolor de espalda por desplazamiento vertebral. Ahora vivo sin dolor."],
        9: ["Diabetes, hipertensión y dolor crónico. La mejora fue integral.", "Múltiples condiciones. Sky Water trabajó en todas simultáneamente."]
    }
    
    months = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    
    testimonials = []
    level_counts = {1: 120, 2: 95, 3: 74, 4: 98, 5: 123, 6: 88, 7: 59, 8: 39, 9: 9}
    
    for level, count in level_counts.items():
        texts = testimonial_texts[level]
        for i in range(count):
            name = random.choice(first_names_female if random.random() > 0.5 else first_names_male)
            testimonials.append(Testimonial(
                name=f"{name} {random.choice(last_initials)}.",
                rating=5,
                location=random.choice(locations),
                level=level,
                level_name=level_names[level],
                text=random.choice(texts),
                date=f"{random.choice(months)} {random.choice(['2024', '2025'])}"
            ))
    
    random.shuffle(testimonials)
    return testimonial

# ============== APPOINTMENTS SYSTEM ==============

class AppointmentSlot(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    patient_email: str
    patient_name: str
    order_id: str
    product_name: str
    status: str = "confirmed"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AppointmentCreate(BaseModel):
    date: str
    time: str
    order_id: str
    patient_email: str
    patient_name: str
    product_name: str

# In-memory appointments storage
appointments_db: List[dict] = []

# Email configuration
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
ADMIN_EMAIL = "salutiumx@gmail.com"

def send_appointment_email(to_email: str, subject: str, html_body: str):
    """Send email using SMTP"""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP not configured, skipping email")
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"Sky Water <{SMTP_USER}>"
        msg['To'] = to_email
        
        html_part = MIMEText(html_body, 'html')
        msg.attach(html_part)
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False

def generate_appointment_confirmation_email(apt_data: dict, product_name: str):
    """Generate HTML email for appointment confirmation"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #000A1A; color: #FFFFFF; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #001428; padding: 30px; border-radius: 12px; }}
            .header {{ text-align: center; border-bottom: 1px solid #00CED1; padding-bottom: 20px; }}
            .logo {{ font-size: 28px; color: #00CED1; font-weight: bold; }}
            .content {{ padding: 20px 0; }}
            .info-box {{ background-color: rgba(0, 206, 209, 0.1); padding: 15px; border-radius: 8px; margin: 15px 0; }}
            .label {{ color: #88C8C8; font-size: 12px; }}
            .value {{ color: #FFFFFF; font-size: 16px; font-weight: bold; }}
            .footer {{ text-align: center; margin-top: 30px; color: #888888; font-size: 12px; }}
            .preparation {{ background-color: #1A1A3A; padding: 15px; border-radius: 8px; margin: 20px 0; }}
            .prep-title {{ color: #00CED1; font-weight: bold; margin-bottom: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">💧 SKY WATER</div>
                <p>Sanación Energética desde el Cielo</p>
            </div>
            <div class="content">
                <h2 style="color: #00CED1;">¡Tu Cita está Confirmada!</h2>
                <p>Hola <strong>{apt_data['patient_name']}</strong>,</p>
                <p>Tu sesión de sanación energética ha sido agendada exitosamente.</p>
                
                <div class="info-box">
                    <div class="label">SERVICIO</div>
                    <div class="value">{product_name}</div>
                </div>
                
                <div class="info-box">
                    <div class="label">FECHA Y HORA</div>
                    <div class="value">{apt_data['date']} a las {apt_data['time']} hrs (UTC-6)</div>
                </div>
                
                <div class="preparation">
                    <div class="prep-title">📋 Preparación para tu Sesión:</div>
                    <ul>
                        <li>Calcula tu agua diaria: peso (kg) × 35ml = ml/día</li>
                        <li>Toma 2 vasos de agua con limón y sal sin refinar</li>
                        <li>Durante la sesión, permanece en posición relajada</li>
                        <li>Puedes estar en casa, trabajo o donde prefieras</li>
                        <li>Evita distracciones durante los 30 minutos</li>
                    </ul>
                </div>
                
                <p>Si tienes alguna pregunta, contáctanos:</p>
                <p><strong>WhatsApp:</strong> +52 55 7851 3603</p>
            </div>
            <div class="footer">
                <p>Sky Water - Donde la ciencia vibracional encuentra tu equilibrio natural</p>
                <p>© 2025 Sky Water. Todos los derechos reservados.</p>
            </div>
        </div>
    </body>
    </html>
    """

def generate_admin_notification_email(apt_data: dict, product_name: str):
    """Generate HTML email for admin notification"""
    # Get weekly calendar
    week_calendar = []
    for apt in appointments_db:
        week_calendar.append(f"- {apt['date']} {apt['time']}: {apt['patient_name']} ({apt['product_name']})")
    
    calendar_html = "<br>".join(week_calendar) if week_calendar else "No hay más citas esta semana"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f5f5f5; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #FFFFFF; padding: 30px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ background-color: #00CED1; color: #FFFFFF; padding: 20px; border-radius: 8px 8px 0 0; margin: -30px -30px 20px -30px; text-align: center; }}
            .alert {{ background-color: #FFF3CD; border-left: 4px solid #FFD700; padding: 15px; margin: 15px 0; }}
            .info-row {{ display: flex; border-bottom: 1px solid #EEE; padding: 10px 0; }}
            .info-label {{ font-weight: bold; width: 150px; color: #666; }}
            .info-value {{ color: #333; }}
            .calendar {{ background-color: #F8F9FA; padding: 15px; border-radius: 8px; margin: 20px 0; }}
            .calendar-title {{ font-weight: bold; color: #00CED1; margin-bottom: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>🔔 Nueva Cita Agendada</h2>
            </div>
            
            <div class="alert">
                <strong>⚡ Nueva reserva recibida</strong>
            </div>
            
            <h3>Información de la Cita:</h3>
            <div class="info-row">
                <span class="info-label">Paciente:</span>
                <span class="info-value">{apt_data['patient_name']}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Email:</span>
                <span class="info-value">{apt_data['patient_email']}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Servicio:</span>
                <span class="info-value">{product_name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Fecha:</span>
                <span class="info-value">{apt_data['date']}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Hora:</span>
                <span class="info-value">{apt_data['time']} hrs (UTC-6)</span>
            </div>
            <div class="info-row">
                <span class="info-label">Orden ID:</span>
                <span class="info-value">{apt_data['order_id']}</span>
            </div>
            
            <div class="calendar">
                <div class="calendar-title">📅 Calendario de la Semana:</div>
                {calendar_html}
            </div>
        </div>
    </body>
    </html>
    """

@api_router.get("/appointments/available-slots")
async def get_available_slots(date: str = None):
    """Get available appointment slots for a given date or next 7 days"""
    from datetime import timedelta
    import pytz
    
    utc_minus_6 = pytz.timezone('America/Mexico_City')
    today = datetime.now(utc_minus_6).date()
    
    # Working hours: 10AM-6PM, lunch break 2PM-4PM
    working_hours = [
        "10:00", "10:30", "11:00", "11:30", 
        "12:00", "12:30", "13:00", "13:30",
        # 14:00-16:00 is lunch break
        "16:00", "16:30", "17:00", "17:30"
    ]
    
    slots = []
    dates_to_check = []
    
    if date:
        dates_to_check = [datetime.strptime(date, "%Y-%m-%d").date()]
    else:
        # Next 14 days
        for i in range(14):
            check_date = today + timedelta(days=i)
            # Only weekdays (Monday=0 to Friday=4)
            if check_date.weekday() < 5:
                dates_to_check.append(check_date)
    
    for check_date in dates_to_check:
        if check_date.weekday() >= 5:  # Skip weekends
            continue
            
        date_str = check_date.strftime("%Y-%m-%d")
        for time_slot in working_hours:
            # Count existing appointments for this slot
            existing = sum(1 for apt in appointments_db 
                         if apt['date'] == date_str and apt['time'] == time_slot)
            
            # Max 2 appointments per slot
            if existing < 2:
                slots.append({
                    "date": date_str,
                    "time": time_slot,
                    "available_spots": 2 - existing
                })
    
    return {"slots": slots}

@api_router.post("/appointments/book")
async def book_appointment(appointment: AppointmentCreate):
    """Book an appointment slot and send confirmation emails"""
    # Check if slot is still available
    existing = sum(1 for apt in appointments_db 
                  if apt['date'] == appointment.date and apt['time'] == appointment.time)
    
    if existing >= 2:
        raise HTTPException(status_code=400, detail="Este horario ya está lleno")
    
    apt_data = {
        "id": str(uuid.uuid4()),
        "date": appointment.date,
        "time": appointment.time,
        "patient_email": appointment.patient_email,
        "patient_name": appointment.patient_name,
        "order_id": appointment.order_id,
        "product_name": appointment.product_name,
        "status": "confirmed",
        "created_at": datetime.utcnow().isoformat()
    }
    
    appointments_db.append(apt_data)
    
    # Send confirmation email to patient
    patient_email_html = generate_appointment_confirmation_email(apt_data, appointment.product_name)
    send_appointment_email(
        appointment.patient_email,
        f"✅ Cita Confirmada - Sky Water - {appointment.date}",
        patient_email_html
    )
    
    # Send notification email to admin
    admin_email_html = generate_admin_notification_email(apt_data, appointment.product_name)
    send_appointment_email(
        ADMIN_EMAIL,
        f"🔔 Nueva Cita: {appointment.patient_name} - {appointment.date} {appointment.time}",
        admin_email_html
    )
    
    return {
        "success": True,
        "appointment": apt_data,
        "message": "Cita agendada exitosamente"
    }

@api_router.get("/appointments/my-appointments/{order_id}")
async def get_my_appointments(order_id: str):
    """Get appointments for a specific order"""
    user_appointments = [apt for apt in appointments_db if apt['order_id'] == order_id]
    return {"appointments": user_appointments}

# ============== HOW IT WORKS - SCIENTIFIC BASIS ==============

@api_router.get("/how-it-works")
async def get_how_it_works():
    """Get the scientific basis and explanation of energy healing"""
    return {
        "title": "¿Cómo Funciona Sky Water?",
        "subtitle": "La Ciencia Detrás de la Sanación Energética",
        "introduction": """
Sky Water utiliza principios de sanación energética a distancia, una práctica respaldada por investigaciones científicas recientes. 
Nuestro método se basa en la transmisión de bioenergía cuántica que opera independientemente de la distancia física, 
permitiendo una conexión energética directa entre el sanador y el receptor.
        """,
        "scientific_studies": [
            {
                "title": "Estudio Clínico Controlado sobre Sanación Energética a Distancia",
                "source": "National Institutes of Health (NIH) - PubMed Central",
                "year": "2024",
                "reference": "PMC11392496",
                "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11392496/",
                "summary": "Un ensayo clínico aleatorizado, doble ciego y controlado con placebo (n=114 adultos) demostró que la sanación energética a distancia mejoró significativamente síntomas psicológicos como fatiga, ansiedad, depresión, problemas de sueño y estrés (p<0.0001). No se reportaron efectos adversos.",
                "key_findings": [
                    "Mejora significativa en todos los síntomas evaluados",
                    "Resultados superiores al grupo placebo y control",
                    "Sin efectos adversos reportados",
                    "Mejora en la calidad de vida general"
                ]
            },
            {
                "title": "Revisión Integral de 353 Estudios Clínicos sobre Terapia de Biocampo",
                "source": "PubMed - Journal of Integrative and Complementary Medicine",
                "year": "2025",
                "reference": "PMID: 39854162",
                "url": "https://pubmed.ncbi.nlm.nih.gov/39854162/",
                "summary": "Una revisión exhaustiva que analizó 353 estudios clínicos revisados por pares (255 ensayos controlados aleatorios) sobre terapias de biocampo. Casi la mitad (172 estudios) reportaron resultados positivos en diversas condiciones de salud.",
                "key_findings": [
                    "353 estudios clínicos analizados",
                    "255 ensayos controlados aleatorios (RCTs)",
                    "172 estudios con resultados positivos",
                    "Efectividad demostrada en dolor, fatiga, ansiedad y más"
                ]
            },
            {
                "title": "Mecanismos Cuánticos en la Terapia de Bioenergía",
                "source": "Healing Warriors Program - Review 2024",
                "year": "2024",
                "reference": "Narrative Review",
                "url": "https://www.healingwarriorsprogram.org/",
                "summary": "Esta revisión narrativa propone mecanismos cuánticos como el entrelazamiento para explicar los efectos de las terapias de biocampo. Documenta evidencia preclínica y clínica que muestra efectividad en dolor, fatiga relacionada con cáncer, estrés y trastornos de salud mental.",
                "key_findings": [
                    "Propuesta de mecanismos cuánticos (entrelazamiento)",
                    "Efectividad en múltiples condiciones",
                    "Base teórica sólida para sanación a distancia",
                    "Integración de física cuántica y biología"
                ]
            }
        ],
        "our_method": {
            "title": "El Método Sky Water",
            "steps": [
                {
                    "step": 1,
                    "title": "Conexión Inicial",
                    "description": "Utilizamos tus datos personales (nombre completo, ubicación, fecha de nacimiento) para establecer una conexión energética única y personalizada."
                },
                {
                    "step": 2,
                    "title": "Análisis Energético",
                    "description": "La descripción detallada de tus síntomas nos permite identificar los bloqueos energéticos específicos que requieren atención."
                },
                {
                    "step": 3,
                    "title": "Transmisión de Bioenergía",
                    "description": "Durante tu cita programada, canalizamos energía sanadora específicamente calibrada para tu condición, utilizando principios de resonancia cuántica."
                },
                {
                    "step": 4,
                    "title": "Integración",
                    "description": "Tu cuerpo integra la energía recibida. Es importante mantenerse hidratado y en un estado receptivo durante y después de la sesión."
                }
            ]
        },
        "preparation_instructions": {
            "title": "Preparación para tu Sesión",
            "water_formula": "Multiplica tu peso en kg por 35ml para obtener tu consumo diario de agua recomendado.",
            "special_water": "Toma al menos 2 vasos de agua con limón y una pizca de sal gruesa sin refinar (sin yodo ni flúor) al día. Si no tienes sal sin refinar, puedes usar sal de mesa común ocasionalmente.",
            "during_session": "Durante la sesión de 30 minutos, permanece en un lugar cómodo (casa, trabajo, donde sea) en posición relajada.",
            "tips": [
                "Estar en un ambiente tranquilo",
                "Posición cómoda (sentado o acostado)",
                "Mantener mente abierta y receptiva",
                "Evitar distracciones durante la sesión",
                "Beber agua antes y después de la sesión"
            ]
        },
        "disclaimer": "Sky Water es un servicio de sanación energética complementaria. No sustituye el diagnóstico, tratamiento o consejo médico profesional."
    }

# ============== CONTACT & SUPPORT ==============

WHATSAPP_NUMBER = "+525578513603"
SUPPORT_EMAIL = "salutiumx@gmail.com"

@api_router.get("/contact")
async def get_contact_info():
    """Get contact information"""
    return {
        "whatsapp": WHATSAPP_NUMBER,
        "whatsapp_link": f"https://wa.me/525578513603",
        "email": SUPPORT_EMAIL,
        "support_hours": "Lunes a Viernes, 10:00 AM - 6:00 PM (UTC-6)",
        "response_time": "Respondemos en menos de 24 horas"
    }

@api_router.get("/guarantee")
async def get_guarantee_info():
    """Get satisfaction guarantee information"""
    return {
        "title": "Garantía de Satisfacción Sky Water",
        "description": "En Sky Water creemos en nuestro servicio. Si después de recibir tu terapia energética no estás satisfecho con los resultados, te devolvemos tu dinero.",
        "conditions": [
            "La solicitud debe realizarse dentro de los 7 días posteriores a tu sesión",
            "Debes haber completado tu sesión en el horario programado",
            "Es necesario proporcionar retroalimentación sobre tu experiencia",
            "El reembolso se procesa por el mismo método de pago original"
        ],
        "how_to_claim": "Contáctanos por WhatsApp para solicitar tu reembolso",
        "whatsapp": WHATSAPP_NUMBER,
        "whatsapp_link": f"https://wa.me/525578513603?text=Hola,%20quiero%20solicitar%20información%20sobre%20la%20garantía%20de%20satisfacción",
        "note": "Nuestro compromiso es tu bienestar. Si no experimentas mejoras, queremos saberlo."
    }

# Include the router (MUST be after all route definitions)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

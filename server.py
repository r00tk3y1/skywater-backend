from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import hashlib
import time
import json
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timedelta
import pytz
import random
import mercadopago
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import httpx
import asyncio

# Google Calendar integration (optional — graceful degradation if not installed)
try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    GOOGLE_CALENDAR_AVAILABLE = False
    logging.warning("google-api-python-client not installed — Google Calendar integration disabled")

# Try to import emergentintegrations, but make it optional
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    EMERGENT_AVAILABLE = True
except ImportError:
    EMERGENT_AVAILABLE = False
    logging.warning("emergentintegrations not available, using direct OpenAI API")

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# LLM Configuration
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

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

# FX rate: USD → MXN (overridable via env var; one-time payment flow still
# hardcodes 17.5 — replace that magic number with USD_TO_MXN in a later PR)
USD_TO_MXN = float(os.environ.get('USD_TO_MXN', '17.5'))

# Subscription tier config (prices in USD; billed in MXN via USD_TO_MXN)
SUBSCRIPTION_TIERS = {
    "rocio":    {"usd": 39.0,  "label": "Rocío"},
    "manantial":{"usd": 97.0,  "label": "Manantial"},
    "fuente":   {"usd": 197.0, "label": "Fuente"},
}

# Google Calendar configuration (stored OAuth2 refresh token — one-time setup)
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REFRESH_TOKEN = os.environ.get('GOOGLE_REFRESH_TOKEN', '')
GOOGLE_CALENDAR_ID = os.environ.get('GOOGLE_CALENDAR_ID', 'primary')

# Telegram instant notifications
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
ADMIN_PIN = os.environ.get('ADMIN_PIN', '000000')

# Meta Conversions API (CAPI)
META_PIXEL_ID = os.environ.get('META_PIXEL_ID', '631454239092950')
META_CAPI_TOKEN = os.environ.get('META_CAPI_TOKEN', '')
META_AD_ACCOUNT = 'act_688124101642557'
META_GRAPH_TOKEN = os.environ.get('META_GRAPH_TOKEN', 'EAAe1IMTlJOoBRV8qt2AtZBZCr3RfXLA8ngD4pKMbKvXjhxw6ie9eMIYOZAXdk7xv1yEanbeMHd1eF7CreUa9xwzL368MQxT7rdNUddjGuHzZAOlZAUx5HFgisBOsMQKuZBgs8Iv18xM381OnaViJQEawZBDvwgvtsJtXnEB2sYEsRZC2yTV59EWJBdLtoXFblwIv0zaFigZDZD')

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
    state: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    birth_date: str
    symptoms: str
    email: str
    rfc: Optional[str] = None

class OrderCreate(BaseModel):
    product_id: str
    patient_data: PatientData
    terms_accepted: bool
    fbp: Optional[str] = None
    fbclid: Optional[str] = None

class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_number: str = Field(default_factory=lambda: f"SKYWATER-{random.randint(10000, 99999)}")
    product_id: str
    product_name: str
    product_price: float
    product_level: Optional[int] = None
    patient_data: PatientData
    terms_accepted: bool
    referral_code: Optional[str] = None
    referral_applied: bool = False
    coupon_code: Optional[str] = None
    coupon_applied: bool = False
    discount_pct: int = 0
    payment_method: Optional[str] = None
    payment_status: str = "pending"
    fbp: Optional[str] = None
    fbclid: Optional[str] = None
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
    referral_code: Optional[str] = None

class SubscribeRequest(BaseModel):
    email: str
    tier: str
    billing_cycle: Optional[str] = "monthly"  # "monthly" | "annual"
    payer_name: Optional[str] = None

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

class TestimonialSubmit(BaseModel):
    name: str
    country: str
    level: int
    level_name: str
    text: str
    rating: int  # 1-5
    email: str
    order_id: str

class PushTokenRegister(BaseModel):
    email: str
    token: str
    platform: str = "unknown"  # "ios" | "android"

class RedeemRewardRequest(BaseModel):
    email: str
    reward_index: int
    order_id: str

# ============== PRODUCTS DATA ==============

PRODUCTS = [
    Product(
        id="level-1",
        level=1,
        name="Sky Water - Primer Contacto",
        icon="compass",
        price=4.99,
        indication="Descubre tu nivel de energía",
        examples="Conoce tu punto de partida en energía, claridad y enfoque",
        description="Tu primer paso con Sky Water. Una lectura de tu nivel de energía para saber dónde estás hoy y por dónde empezar a sentirte con más vitalidad. Experiencia de bienestar.",
        badge="Primer Paso"
    ),
    Product(
        id="level-2",
        level=2,
        name="Sky Water - Pulso Inicial",
        icon="zap",
        price=19.99,
        indication="Tu primera experiencia de energía",
        examples="Ideal para sentir por primera vez la energía Sky Water",
        description="Perfecto si es tu primera vez o eres escéptico. Una micro-dosis de energía para que experimentes y sientas por ti mismo el efecto Sky Water. Sin compromiso, máxima experiencia.",
        badge="Para Nuevos y Escépticos"
    ),
    Product(
        id="level-3",
        level=3,
        name="Sky Water - Onda Suave",
        icon="radio",
        price=49.99,
        indication="Energía y bienestar sostenido",
        examples="Para mantener tu energía, claridad y ánimo día a día",
        description="Ya sentiste el efecto y quieres más. Este nivel desbloquea una carga de energía mayor para sostener tu vitalidad y presencia. Para quienes están listos para el siguiente paso en su bienestar.",
        badge="Energía Potenciada"
    ),
    Product(
        id="level-4",
        level=4,
        name="Sky Water - Corriente Activa",
        icon="activity",
        price=97,
        indication="Recarga intensa de energía",
        examples="Para días exigentes en los que necesitas energía y enfoque al máximo",
        description="Una sesión completa de 60 minutos de energía de alta frecuencia para recargarte a fondo cuando más lo necesitas. Vitalidad y claridad para cuando el día no da tregua.",
        badge="Recarga Rápida"
    ),
    Product(
        id="level-5",
        level=5,
        name="Sky Water - Inmersión Profunda",
        icon="layers",
        price=197,
        indication="Bienestar profundo y constante",
        examples="Para quienes buscan constancia en su energía y equilibrio",
        description="Paquete de 3 sesiones para un bienestar que dura. La vitalidad se construye con constancia: trabajamos en capas para liberar tu energía y restaurar tu equilibrio natural.",
        badge="Más Popular"
    ),
    Product(
        id="level-6",
        level=6,
        name="Sky Water - Resonancia Avanzada",
        icon="globe",
        price=397,
        indication="Energía sostenida y recuperación",
        examples="Para sostener tu vitalidad y recuperarte del desgaste diario",
        description="Programa de 6 sesiones para mantener tu energía en alto de forma sostenida. Ideal cuando el ritmo de vida te desgasta y quieres recuperar tu vitalidad y presencia.",
        badge="Recuperación"
    ),
    Product(
        id="level-7",
        level=7,
        name="Sky Water - Onda Expandida",
        icon="sun",
        price=697,
        indication="Transformación de tu energía",
        examples="Para un cambio profundo y sostenido en tu vitalidad y enfoque",
        description="Programa trimestral de 12 sesiones con seguimiento personalizado. Para un cambio profundo y duradero en tu energía, claridad y bienestar general.",
        badge="Bienestar Profundo"
    ),
    Product(
        id="level-8",
        level=8,
        name="Sky Water - Plenitud Total",
        icon="maximize-2",
        price=997,
        indication="Bienestar integral intensivo",
        examples="Para una transformación completa de tu energía y bienestar",
        description="Programa semestral de 24 sesiones. Una experiencia intensiva de bienestar para renovar por completo tu energía, equilibrio y vitalidad, con acompañamiento personalizado.",
        badge="Experiencia Intensiva"
    ),
    Product(
        id="level-9",
        level=9,
        name="Sky Water - Transformación Total",
        icon="infinity",
        price=1997,
        indication="Bienestar ilimitado",
        examples="La experiencia completa Sky Water para tu vitalidad total",
        description="Programa anual con sesiones ilimitadas. La experiencia definitiva de Sky Water: energía, claridad y bienestar sin límites, con acceso prioritario y atención personalizada. Tu mayor inversión en ti.",
        badge="Transformación Total"
    ),
    Product(
        id="tripwire",
        level=0,
        name="Sky Water - Sesión de Activación",
        icon="zap",
        price=9.97,
        indication="Tu primera sesión de energía Sky Water",
        examples="Energía, claridad y enfoque para tu día a día",
        description="Tu primera sesión de Sky Water, sin mensualidad. Una experiencia de bienestar para sentir más energía, claridad y presencia. (Experiencia de bienestar, no es un tratamiento médico.)",
        badge="Oferta de entrada"
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
        product_level=product.level,
        patient_data=order_data.patient_data,
        terms_accepted=order_data.terms_accepted,
        fbp=order_data.fbp,
        fbclid=order_data.fbclid
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

    # Resolver descuento SERVER-SIDE (cupón canjeado o código de referido). Nunca confiar en el cliente.
    disc = await resolve_discount_code(data.referral_code, order_obj.patient_data.email)
    discount_pct = disc["discount_pct"]
    if disc["kind"]:
        await db.orders.update_one(
            {"id": order_obj.id},
            {"$set": {
                "referral_code": disc["referral_code"],
                "coupon_code": disc["coupon_code"],
                "discount_pct": discount_pct,
            }},
        )

    unit_price = round(order_obj.product_price * 17.5 * (1 - discount_pct / 100), 2)

    preference_data = {
        "items": [
            {
                "id": order_obj.product_id,
                "title": f"Sky Water - {order_obj.product_name}",
                "description": "Sky Water - Experiencia de bienestar",
                "quantity": 1,
                "currency_id": "MXN",
                "unit_price": unit_price
            }
        ],
        "payer": {
            "email": order_obj.patient_data.email,
            "name": f"{order_obj.patient_data.first_name} {order_obj.patient_data.first_lastname}",
            **({"identification": {"type": "RFC", "number": order_obj.patient_data.rfc}} if order_obj.patient_data.rfc else {}),
        },
        "external_reference": order_obj.id,
        "back_urls": {
            "success": f"https://skywater.site/checkout/confirmation?order_id={order_obj.id}&status=approved",
            "failure": f"https://skywater.site/checkout/payment?order_id={order_obj.id}&status=failure",
            "pending": f"https://skywater.site/checkout/payment?order_id={order_obj.id}&status=pending"
        },
        "auto_return": "approved",
        "notification_url": "https://skywater-backend-production-cc33.up.railway.app/api/mercadopago/webhook",
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
            
            # Auto-detect test vs production mode by token prefix
            is_test_mode = MERCADO_PAGO_ACCESS_TOKEN.startswith('TEST-')
            checkout_url = preference.get("sandbox_init_point", preference["init_point"]) if is_test_mode else preference["init_point"]

            return {
                "preference_id": preference["id"],
                "init_point": checkout_url,
                "sandbox_init_point": preference.get("sandbox_init_point", preference["init_point"]),
                "is_test_mode": is_test_mode,
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
        
        event_type = payload.get("type", "")

        # ── One-time payment branch (unchanged) ──────────────────────────────
        if event_type == "payment":
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

                        # Tripwire/ventas: notificar Purchase a Meta (CAPI) al aprobarse el pago.
                        # event_id = order.id para deduplicar con el fbq('Purchase') del front.
                        if payment_status == "approved":
                            paid_order = await db.orders.find_one({"id": external_reference})
                            if paid_order:
                                asyncio.create_task(fire_capi_event(
                                    event_name="Purchase",
                                    request=request,
                                    fbp=paid_order.get("fbp"),
                                    fbclid=paid_order.get("fbclid"),
                                    event_id=paid_order["id"],
                                    custom_data={
                                        "value": paid_order.get("product_price", 0),
                                        "currency": "USD",
                                        "content_type": "product",
                                        "content_ids": [paid_order.get("product_id", "tripwire")],
                                    },
                                ))

                                # Referido: registrar SERVER-SIDE sobre pago verificado (anti-farmeo).
                                ref_code = paid_order.get("referral_code")
                                if ref_code and not paid_order.get("referral_applied"):
                                    buyer = (paid_order.get("patient_data") or {}).get("email", "")
                                    try:
                                        res = await register_referral_atomic(ref_code, buyer)
                                        await db.orders.update_one(
                                            {"id": external_reference},
                                            {"$set": {"referral_applied": True}},
                                        )
                                        logger.info(f"Referral apply ({ref_code}) order {external_reference}: {res}")
                                    except Exception as e:
                                        logger.error(f"Referral register failed {external_reference}: {e}")

                                # Cupón de recompensa: marcar usado de forma atómica sobre pago verificado.
                                coupon_code = paid_order.get("coupon_code")
                                if coupon_code and not paid_order.get("coupon_applied"):
                                    try:
                                        await db.coupons.update_one(
                                            {"code": coupon_code, "used": False},
                                            {"$set": {"used": True, "used_at": datetime.utcnow().isoformat(),
                                                      "used_order_id": external_reference}},
                                        )
                                        await db.orders.update_one(
                                            {"id": external_reference},
                                            {"$set": {"coupon_applied": True}},
                                        )
                                    except Exception as e:
                                        logger.error(f"Coupon redeem failed {external_reference}: {e}")

        # ── Subscription / preapproval branch (new) ──────────────────────────
        elif event_type in ("subscription_preapproval", "preapproval", "subscription_authorized_payment"):
            resource_id = payload.get("data", {}).get("id")

            if resource_id and mp_sdk:
                # For authorized recurring payments, fetch the underlying preapproval
                if event_type == "subscription_authorized_payment":
                    # authorized_payment object contains preapproval_id
                    auth_response = mp_sdk.authorized_payment().get(resource_id)
                    if auth_response.get("status") == 200:
                        auth_obj = auth_response["response"]
                        preapproval_id = auth_obj.get("preapproval_id")
                        payment_status_raw = auth_obj.get("status", "")
                        # Record the individual recurring payment
                        if preapproval_id:
                            await db.subscription_payments.insert_one({
                                "id": str(uuid.uuid4()),
                                "preapproval_id": preapproval_id,
                                "authorized_payment_id": str(resource_id),
                                "status": payment_status_raw,
                                "amount": auth_obj.get("transaction_amount"),
                                "currency_id": auth_obj.get("currency_id", "MXN"),
                                "recorded_at": datetime.utcnow(),
                            })
                            if payment_status_raw == "processed":
                                await db.subscriptions.update_one(
                                    {"preapproval_id": preapproval_id},
                                    {"$set": {
                                        "status": "authorized",
                                        "last_payment_at": datetime.utcnow(),
                                    }}
                                )
                else:
                    # subscription_preapproval or preapproval: fetch the preapproval object
                    pa_response = mp_sdk.preapproval().get(resource_id)
                    if pa_response.get("status") == 200:
                        pa = pa_response["response"]
                        pa_status = pa.get("status", "")
                        # Map MP statuses to internal statuses
                        sub_status_map = {
                            "authorized": "authorized",
                            "pending": "pending",
                            "paused": "paused",
                            "cancelled": "cancelled",
                        }
                        mapped_status = sub_status_map.get(pa_status, pa_status)
                        update_fields = {"status": mapped_status}
                        if pa_status == "authorized":
                            update_fields["authorized_at"] = datetime.utcnow()
                        await db.subscriptions.update_one(
                            {"preapproval_id": str(resource_id)},
                            {"$set": update_fields}
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

# ============== SUBSCRIPTION (RECURRING) ROUTES ==============

@api_router.post("/mercadopago/subscribe")
async def create_subscription(data: SubscribeRequest):
    """Create a MercadoPago Preapproval (recurring subscription) for the given tier."""
    if not mp_sdk:
        raise HTTPException(status_code=500, detail="Mercado Pago not configured")

    tier_key = data.tier.lower()
    if tier_key not in SUBSCRIPTION_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{data.tier}'. Valid options: {list(SUBSCRIPTION_TIERS.keys())}"
        )

    tier_cfg = SUBSCRIPTION_TIERS[tier_key]

    # Amount is computed SERVER-SIDE from the tier + cycle. Never trust a client-sent amount.
    cycle = (data.billing_cycle or "monthly").lower()
    if cycle not in ("monthly", "annual"):
        cycle = "monthly"
    if cycle == "annual":
        # "Paga 10, llévate 12": el cargo anual = 10 mensualidades, cobrado 1 vez al año.
        usd_charge = tier_cfg["usd"] * 10
        frequency, frequency_type = 12, "months"
    else:
        usd_charge = tier_cfg["usd"]
        frequency, frequency_type = 1, "months"
    amount_mxn = round(usd_charge * USD_TO_MXN, 2)

    preapproval_data = {
        "reason": f"Sky Water - Membresia {tier_cfg['label']} ({'Anual' if cycle == 'annual' else 'Mensual'})",
        "payer_email": data.email,
        "auto_recurring": {
            "frequency": frequency,
            "frequency_type": frequency_type,
            "transaction_amount": amount_mxn,
            "currency_id": "MXN",
        },
        "back_url": "https://skywater.site/checkout/confirmation",
        "status": "pending",
    }

    try:
        response = mp_sdk.preapproval().create(preapproval_data)

        if response["status"] not in (200, 201):
            raise HTTPException(status_code=400, detail="Error creating preapproval with MercadoPago")

        preapproval = response["response"]
        preapproval_id = preapproval.get("id")
        init_point = preapproval.get("init_point")

        # Persist to db.subscriptions
        subscription_doc = {
            "id": str(uuid.uuid4()),
            "email": data.email,
            "tier": tier_key,
            "preapproval_id": preapproval_id,
            "status": "pending",
            "billing_cycle": cycle,
            "created_at": datetime.utcnow(),
            "amount_mxn": amount_mxn,
        }
        await db.subscriptions.insert_one(subscription_doc)

        return {
            "preapproval_id": preapproval_id,
            "init_point": init_point,
            "tier": tier_key,
            "billing_cycle": cycle,
            "amount_mxn": amount_mxn,
            "email": data.email,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating subscription: {str(e)}")


@api_router.get("/mercadopago/subscription-status/{email}")
async def get_subscription_status(email: str):
    """Return the active (or most recent) subscription for a given email."""
    # Prefer authorized, then pending, then any other status
    priority_order = ["authorized", "pending", "paused", "cancelled"]
    subscription = None
    for status in priority_order:
        doc = await db.subscriptions.find_one(
            {"email": email, "status": status},
            sort=[("created_at", -1)]
        )
        if doc:
            subscription = doc
            break

    if not subscription:
        # Fall back to the most recent record regardless of status
        subscription = await db.subscriptions.find_one(
            {"email": email},
            sort=[("created_at", -1)]
        )

    if not subscription:
        raise HTTPException(status_code=404, detail="No subscription found for this email")

    return {
        "email": email,
        "tier": subscription.get("tier"),
        "status": subscription.get("status"),
        "preapproval_id": subscription.get("preapproval_id"),
        "amount_mxn": subscription.get("amount_mxn"),
        "created_at": subscription.get("created_at"),
        "last_payment_at": subscription.get("last_payment_at"),
    }


class ContributionRequest(BaseModel):
    amount: float
    description: str = "Sky Water Contribution"

@api_router.post("/mercadopago/contribution")
async def create_contribution(data: ContributionRequest):
    """Create a Mercado Pago preference for voluntary contributions"""
    if not mp_sdk:
        raise HTTPException(status_code=400, detail="Mercado Pago not configured")
    
    try:
        preference_data = {
            "items": [{
                "title": "Contribución a Sky Water",
                "description": data.description,
                "quantity": 1,
                "currency_id": "USD",
                "unit_price": float(data.amount)
            }],
            "back_urls": {
                "success": "https://skywater-five.vercel.app/",
                "failure": "https://skywater-five.vercel.app/",
                "pending": "https://skywater-five.vercel.app/"
            },
            "auto_return": "approved",
            "statement_descriptor": "SKYWATER CONTRIB"
        }
        
        preference_response = mp_sdk.preference().create(preference_data)
        
        if preference_response["status"] == 201:
            preference = preference_response["response"]
            return {
                "preference_id": preference["id"],
                "init_point": preference["init_point"]
            }
        else:
            raise HTTPException(status_code=400, detail="Error creating contribution preference")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating contribution: {str(e)}")

# ============== SYMPTOM ANALYZER CHATBOT ==============

class SymptomAnalysisRequest(BaseModel):
    symptoms: str
    language: str = "es"
    session_id: Optional[str] = None

class SymptomAnalysisResponse(BaseModel):
    analysis: str
    recommended_level: int
    level_name: str
    level_description: str
    session_id: str

LEVEL_INFO = {
    "es": {
        1: {"name": "Sky Water - Primer Contacto", "description": "Sesión diagnóstica de 30 min. Indicada para quienes desean una evaluación inicial sin síntomas activos o buscan orientación preventiva."},
        2: {"name": "Sky Water - Pulso Inicial", "description": "Sesión de 30 min. Para fatiga leve ocasional, cefaleas esporádicas, estrés puntual o usuarios que se inician en la terapia energética."},
        3: {"name": "Sky Water - Onda Suave", "description": "Sesión de 45 min. Para fatiga recurrente, cefaleas frecuentes, lumbalgia o cervicalgia persistente, insomnio moderado y ansiedad leve."},
        4: {"name": "Sky Water - Corriente Activa", "description": "Sesión intensiva de 60 min. Para dolor agudo intenso, migraña recurrente, artralgia notable, trastorno de ansiedad, desequilibrio hormonal o patología digestiva funcional (gastritis, SII)."},
        5: {"name": "Sky Water - Inmersión Profunda", "description": "Sesión profunda de 90 min. Para condiciones crónicas de meses o años: fibromialgia, síndrome de fatiga crónica, depresión clínica, endometriosis, disfunción tiroidea o dolor neuropático."},
        6: {"name": "Sky Water - Resonancia Avanzada", "description": "Sesión avanzada de 2 horas. Para múltiples patologías simultáneas, enfermedad autoinmune establecida, neuropatía periférica, TEPT con somatización o trastornos hormonales complejos."},
        7: {"name": "Sky Water - Onda Expandida", "description": "Sesión premium de 2.5 horas. Para recuperación post-quirúrgica, COVID prolongado, disautonomía, insuficiencia suprarrenal severa o afectación multiorgánica."},
        8: {"name": "Sky Water - Sanación Máxima", "description": "Sesión máxima de 3 horas. Para enfermedades degenerativas, sintomatología neurológica grave, recuperación post-quimioterapia o patología psiquiátrica severa con componente somático."},
        9: {"name": "Sky Water - Transformación Total", "description": "Sesiones extendidas hasta mejoría sostenida. Para cuadros críticos, enfermedades terminales o crónicas multi-sistémicas de alta complejidad que requieren intervención continua."}
    },
    "en": {
        1: {"name": "Sky Water - First Contact", "description": "30-min diagnostic session. Indicated for those seeking an initial assessment without active symptoms or looking for preventive guidance."},
        2: {"name": "Sky Water - Initial Pulse", "description": "30-min session. For occasional mild fatigue, sporadic headaches, situational stress, or first-time users exploring energy therapy."},
        3: {"name": "Sky Water - Gentle Wave", "description": "45-min session. For recurring fatigue, frequent headaches, persistent back or neck pain, moderate insomnia, and mild anxiety disorder."},
        4: {"name": "Sky Water - Active Current", "description": "Intensive 60-min session. For intense acute pain, recurrent migraines, notable joint pain, anxiety disorder, hormonal imbalance, or functional digestive pathology (gastritis, IBS)."},
        5: {"name": "Sky Water - Deep Immersion", "description": "Deep 90-min session. For chronic conditions lasting months or years: fibromyalgia, chronic fatigue syndrome, clinical depression, endometriosis, thyroid dysfunction, or neuropathic pain."},
        6: {"name": "Sky Water - Advanced Resonance", "description": "Advanced 2-hour session. For multiple simultaneous pathologies, established autoimmune disease, peripheral neuropathy, PTSD with somatic manifestation, or complex hormonal disorders."},
        7: {"name": "Sky Water - Expanded Wave", "description": "Premium 2.5-hour session. For post-surgical recovery, long COVID, dysautonomia, severe adrenal insufficiency, or multi-organ involvement."},
        8: {"name": "Sky Water - Maximum Healing", "description": "Maximum 3-hour session. For degenerative diseases, severe neurological symptoms, post-chemotherapy recovery, or severe psychiatric pathology with somatic component."},
        9: {"name": "Sky Water - Total Transformation", "description": "Extended sessions until sustained improvement. For critical, terminal, or high-complexity multi-systemic chronic conditions requiring continuous intervention."}
    },
    "de": {
        1: {"name": "Sky Water - Erstkontakt", "description": "30-min Diagnosesitzung. Für Personen ohne aktive Symptome, die eine erste Bewertung oder präventive Orientierung suchen."},
        2: {"name": "Sky Water - Erster Impuls", "description": "30-min Sitzung. Für gelegentliche leichte Müdigkeit, sporadische Kopfschmerzen, situativen Stress oder Erstnutzer."},
        3: {"name": "Sky Water - Sanfte Welle", "description": "45-min Sitzung. Für wiederkehrende Müdigkeit, häufige Kopfschmerzen, anhaltende Rücken- oder Nackenschmerzen, moderaten Schlafmangel und leichte Angststörung."},
        4: {"name": "Sky Water - Aktiver Strom", "description": "Intensive 60-min Sitzung. Für starke akute Schmerzen, wiederkehrende Migräne, deutliche Gelenkschmerzen, Angststörungen, hormonelles Ungleichgewicht oder funktionelle Verdauungspathologie."},
        5: {"name": "Sky Water - Tiefe Immersion", "description": "Tiefe 90-min Sitzung. Für chronische Erkrankungen seit Monaten oder Jahren: Fibromyalgie, chronisches Müdigkeitssyndrom, klinische Depression, Endometriose, Schilddrüsenfunktionsstörung."},
        6: {"name": "Sky Water - Fortgeschrittene Resonanz", "description": "Fortgeschrittene 2-Stunden-Sitzung. Für mehrere gleichzeitige Pathologien, etablierte Autoimmunerkrankung, periphere Neuropathie, PTBS mit Somatisierung."},
        7: {"name": "Sky Water - Erweiterte Welle", "description": "Premium 2,5-Stunden-Sitzung. Für postoperative Erholung, Long COVID, Dysautonomie, schwere Nebenniereninsuffizienz oder Multiorganbefall."},
        8: {"name": "Sky Water - Maximale Heilung", "description": "Maximale 3-Stunden-Sitzung. Für degenerative Erkrankungen, schwere neurologische Symptome, Erholung nach Chemotherapie oder schwere psychiatrische Pathologie."},
        9: {"name": "Sky Water - Totale Transformation", "description": "Erweiterte Sitzungen bis zur nachhaltigen Verbesserung. Für kritische, terminale oder hochkomplexe multi-systemische chronische Erkrankungen."}
    },
    "it": {
        1: {"name": "Sky Water - Primo Contatto", "description": "Sessione diagnostica di 30 min. Indicata per chi cerca una valutazione iniziale senza sintomi attivi o orientamento preventivo."},
        2: {"name": "Sky Water - Impulso Iniziale", "description": "Sessione di 30 min. Per affaticamento lieve occasionale, cefalee sporadiche, stress situazionale o utenti alle prime armi."},
        3: {"name": "Sky Water - Onda Gentile", "description": "Sessione di 45 min. Per affaticamento ricorrente, cefalee frequenti, lombalgia o cervicalgia persistente, insonnia moderata e disturbo d'ansia lieve."},
        4: {"name": "Sky Water - Corrente Attiva", "description": "Sessione intensiva di 60 min. Per dolore acuto intenso, emicrania ricorrente, artralgia significativa, disturbo d'ansia, squilibrio ormonale o patologia digestiva funzionale."},
        5: {"name": "Sky Water - Immersione Profonda", "description": "Sessione profonda di 90 min. Per condizioni croniche da mesi o anni: fibromialgia, sindrome da fatica cronica, depressione clinica, endometriosi, disfunzione tiroidea."},
        6: {"name": "Sky Water - Risonanza Avanzata", "description": "Sessione avanzata di 2 ore. Per più patologie simultanee, malattia autoimmune stabilita, neuropatia periferica, PTSD con somatizzazione o disturbi ormonali complessi."},
        7: {"name": "Sky Water - Onda Espansa", "description": "Sessione premium di 2,5 ore. Per recupero post-chirurgico, long COVID, disautonomia, insufficienza surrenalica severa o coinvolgimento multi-organo."},
        8: {"name": "Sky Water - Guarigione Massima", "description": "Sessione massima di 3 ore. Per malattie degenerative, sintomi neurologici gravi, recupero post-chemioterapia o patologia psichiatrica severa con componente somatica."},
        9: {"name": "Sky Water - Trasformazione Totale", "description": "Sessioni prolungate fino al miglioramento sostenuto. Per quadri critici, terminali o cronici multi-sistemici ad alta complessità che richiedono intervento continuo."}
    },
    "pt": {
        1: {"name": "Sky Water - Primeiro Contato", "description": "Sessão diagnóstica de 30 min. Indicada para quem busca uma avaliação inicial sem sintomas ativos ou orientação preventiva."},
        2: {"name": "Sky Water - Pulso Inicial", "description": "Sessão de 30 min. Para fadiga leve ocasional, cefaleias esporádicas, estresse pontual ou usuários iniciantes na terapia energética."},
        3: {"name": "Sky Water - Onda Suave", "description": "Sessão de 45 min. Para fadiga recorrente, cefaleias frequentes, lombalgia ou cervicalgia persistente, insônia moderada e ansiedade leve."},
        4: {"name": "Sky Water - Corrente Ativa", "description": "Sessão intensiva de 60 min. Para dor aguda intensa, enxaqueca recorrente, artralgia notável, transtorno de ansiedade, desequilíbrio hormonal ou patologia digestiva funcional (gastrite, SII)."},
        5: {"name": "Sky Water - Imersão Profunda", "description": "Sessão profunda de 90 min. Para condições crônicas de meses ou anos: fibromialgia, síndrome de fadiga crônica, depressão clínica, endometriose, disfunção tireoidiana ou dor neuropática."},
        6: {"name": "Sky Water - Ressonância Avançada", "description": "Sessão avançada de 2 horas. Para múltiplas patologias simultâneas, doença autoimune estabelecida, neuropatia periférica, TEPT com somatização ou distúrbios hormonais complexos."},
        7: {"name": "Sky Water - Onda Expandida", "description": "Sessão premium de 2,5 horas. Para recuperação pós-cirúrgica, COVID longa, disautonomia, insuficiência adrenal severa ou acometimento multiorgânico."},
        8: {"name": "Sky Water - Cura Máxima", "description": "Sessão máxima de 3 horas. Para doenças degenerativas, sintomatologia neurológica grave, recuperação pós-quimioterapia ou patologia psiquiátrica severa com componente somático."},
        9: {"name": "Sky Water - Transformação Total", "description": "Sessões estendidas até melhora sustentada. Para quadros críticos, terminais ou crônicos multi-sistêmicos de alta complexidade que requerem intervenção contínua."}
    },
    "fr": {
        1: {"name": "Sky Water - Premier Contact", "description": "Séance diagnostique de 30 min. Indiquée pour les personnes cherchant une évaluation initiale sans symptômes actifs ou une orientation préventive."},
        2: {"name": "Sky Water - Impulsion Initiale", "description": "Séance de 30 min. Pour fatigue légère occasionnelle, céphalées sporadiques, stress situationnel ou premiers utilisateurs."},
        3: {"name": "Sky Water - Onde Douce", "description": "Séance de 45 min. Pour fatigue récurrente, céphalées fréquentes, lombalgie ou cervicalgie persistante, insomnie modérée et trouble anxieux léger."},
        4: {"name": "Sky Water - Courant Actif", "description": "Séance intensive de 60 min. Pour douleur aiguë intense, migraine récurrente, arthralgie notable, trouble anxieux, déséquilibre hormonal ou pathologie digestive fonctionnelle (gastrite, SCI)."},
        5: {"name": "Sky Water - Immersion Profonde", "description": "Séance profonde de 90 min. Pour conditions chroniques depuis des mois ou années : fibromyalgie, syndrome de fatigue chronique, dépression clinique, endométriose, dysfonction thyroïdienne."},
        6: {"name": "Sky Water - Résonance Avancée", "description": "Séance avancée de 2 heures. Pour plusieurs pathologies simultanées, maladie auto-immune établie, neuropathie périphérique, TSPT avec somatisation ou troubles hormonaux complexes."},
        7: {"name": "Sky Water - Onde Étendue", "description": "Séance premium de 2,5 heures. Pour récupération post-chirurgicale, COVID long, dysautonomie, insuffisance surrénalienne sévère ou atteinte multi-organes."},
        8: {"name": "Sky Water - Guérison Maximale", "description": "Séance maximale de 3 heures. Pour maladies dégénératives, symptômes neurologiques graves, récupération post-chimiothérapie ou pathologie psychiatrique sévère avec composante somatique."},
        9: {"name": "Sky Water - Transformation Totale", "description": "Séances prolongées jusqu'à amélioration durable. Pour tableaux critiques, terminaux ou chroniques multi-systémiques de haute complexité nécessitant une intervention continue."}
    },
    "ja": {
        1: {"name": "Sky Water - ファーストコンタクト", "description": "30分診断セッション。活動性症状のない方や予防的ガイダンスを求める方向けの初期評価。"},
        2: {"name": "Sky Water - 初期パルス", "description": "30分セッション。軽度の疲労感、散発的な頭痛、状況的なストレス、または初めてエネルギー療法を試す方向け。"},
        3: {"name": "Sky Water - 穏やかな波動", "description": "45分セッション。繰り返す疲労、頻繁な頭痛、持続的な腰痛・頸部痛、中等度不眠、軽度不安障害に対応。"},
        4: {"name": "Sky Water - アクティブカレント", "description": "集中60分セッション。強い急性疼痛、反復性片頭痛、関節痛、不安障害、ホルモンバランス異常、機能性消化器疾患（胃炎・過敏性腸症候群）に対応。"},
        5: {"name": "Sky Water - 深部イマージョン", "description": "深い90分セッション。数ヶ月・数年続く慢性疾患：線維筋痛症、慢性疲労症候群、臨床的うつ病、子宮内膜症、甲状腺機能障害、神経障害性疼痛に対応。"},
        6: {"name": "Sky Water - 高度なレゾナンス", "description": "高度な2時間セッション。複数同時病態、確立した自己免疫疾患、末梢神経障害、身体化を伴うPTSD、複雑なホルモン障害に対応。"},
        7: {"name": "Sky Water - 拡張波動", "description": "プレミアム2.5時間セッション。術後回復、ロングCOVID、自律神経失調症、重度副腎不全、多臓器関与に対応。"},
        8: {"name": "Sky Water - 最大ヒーリング", "description": "最大3時間セッション。変性疾患、重篤な神経症状、化学療法後回復、身体的要素を伴う重篤な精神疾患に対応。"},
        9: {"name": "Sky Water - 完全変容", "description": "持続的改善まで延長セッション。継続的介入を要する重篤・末期・高複雑度の多系統慢性疾患に対応。"}
    },
    "ar": {
        1: {"name": "Sky Water - التواصل الأول", "description": "جلسة تشخيصية 30 دقيقة. مخصصة لمن يسعى للتقييم الأولي دون أعراض نشطة أو التوجيه الوقائي."},
        2: {"name": "Sky Water - النبض الأولي", "description": "جلسة 30 دقيقة. للإرهاق الخفيف المتقطع، الصداع العرضي، التوتر الظرفي، أو المستخدمين الجدد."},
        3: {"name": "Sky Water - الموجة اللطيفة", "description": "جلسة 45 دقيقة. للإرهاق المتكرر، الصداع المتكرر، آلام الظهر أو الرقبة المستمرة، الأرق المعتدل، واضطراب القلق الخفيف."},
        4: {"name": "Sky Water - التيار النشط", "description": "جلسة مكثفة 60 دقيقة. للألم الحاد الشديد، الصداع النصفي المتكرر، آلام المفاصل الواضحة، اضطراب القلق، اختلال هرموني، أو أمراض الجهاز الهضمي الوظيفية (التهاب المعدة، القولون العصبي)."},
        5: {"name": "Sky Water - الغمر العميق", "description": "جلسة عميقة 90 دقيقة. للأمراض المزمنة التي تستمر شهوراً أو سنوات: الفيبروميالجيا، متلازمة التعب المزمن، الاكتئاب السريري، بطانة الرحم المهاجرة، خلل وظيفة الغدة الدرقية."},
        6: {"name": "Sky Water - الرنين المتقدم", "description": "جلسة متقدمة ساعتين. لأمراض متعددة متزامنة، مرض مناعي ذاتي راسخ، اعتلال الأعصاب الطرفي، اضطراب ما بعد الصدمة مع تجسيم جسدي."},
        7: {"name": "Sky Water - الموجة الموسعة", "description": "جلسة مميزة 2.5 ساعة. للتعافي بعد الجراحة، COVID الطويل، خلل الجهاز العصبي اللاإرادي، قصور الغدة الكظرية الحاد، أو تأثر أعضاء متعددة."},
        8: {"name": "Sky Water - الشفاء الأقصى", "description": "جلسة قصوى 3 ساعات. للأمراض التنكسية، الأعراض العصبية الشديدة، التعافي بعد العلاج الكيميائي، أو اضطراب نفسي شديد مع مكون جسدي."},
        9: {"name": "Sky Water - التحول الكامل", "description": "جلسات ممتدة حتى التحسن المستدام. للحالات الحرجة أو المزمنة متعددة الأجهزة عالية التعقيد التي تستلزم تدخلاً مستمراً."}
    },
    "ru": {
        1: {"name": "Sky Water - Первый Контакт", "description": "Диагностический сеанс 30 мин. Для первичной оценки без активных симптомов или профилактической консультации."},
        2: {"name": "Sky Water - Начальный Импульс", "description": "Сеанс 30 мин. При лёгкой периодической усталости, эпизодических головных болях, ситуативном стрессе или для новых пользователей."},
        3: {"name": "Sky Water - Мягкая Волна", "description": "Сеанс 45 мин. При рецидивирующей усталости, частых головных болях, стойких болях в спине или шее, умеренной бессоннице и лёгком тревожном расстройстве."},
        4: {"name": "Sky Water - Активный Поток", "description": "Интенсивный сеанс 60 мин. При сильной острой боли, рецидивирующей мигрени, выраженной артралгии, тревожном расстройстве, гормональном дисбалансе или функциональной патологии ЖКТ (гастрит, СРК)."},
        5: {"name": "Sky Water - Глубокое Погружение", "description": "Глубокий сеанс 90 мин. При хронических состояниях месяцами или годами: фибромиалгия, синдром хронической усталости, клиническая депрессия, эндометриоз, дисфункция щитовидной железы."},
        6: {"name": "Sky Water - Продвинутый Резонанс", "description": "Продвинутый 2-часовой сеанс. При множественных одновременных патологиях, установленном аутоиммунном заболевании, периферической нейропатии, ПТСР с соматизацией."},
        7: {"name": "Sky Water - Расширенная Волна", "description": "Премиум 2,5-часовой сеанс. При постоперационном восстановлении, Long COVID, дисавтономии, тяжёлой надпочечниковой недостаточности или полиорганном поражении."},
        8: {"name": "Sky Water - Максимальное Исцеление", "description": "Максимальный 3-часовой сеанс. При дегенеративных заболеваниях, тяжёлой неврологической симптоматике, восстановлении после химиотерапии или тяжёлой психической патологии с соматическим компонентом."},
        9: {"name": "Sky Water - Полная Трансформация", "description": "Расширенные сеансы до устойчивого улучшения. Для критических, терминальных или высококомплексных полисистемных хронических состояний, требующих непрерывного вмешательства."}
    },
    "zh": {
        1: {"name": "Sky Water - 首次接触", "description": "30分钟诊断疗程。适合无活跃症状、寻求初步评估或预防性指导的用户。"},
        2: {"name": "Sky Water - 初始脉冲", "description": "30分钟疗程。针对偶发轻度疲劳、散发性头痛、情境性压力或首次尝试能量疗愈的用户。"},
        3: {"name": "Sky Water - 柔和波动", "description": "45分钟疗程。针对反复疲劳、频繁头痛、持续腰背或颈部疼痛、中度失眠及轻度焦虑障碍。"},
        4: {"name": "Sky Water - 活跃流动", "description": "60分钟强化疗程。针对强烈急性疼痛、反复偏头痛、明显关节痛、焦虑障碍、激素失调或功能性消化系统疾病（胃炎、肠易激综合征）。"},
        5: {"name": "Sky Water - 深度浸入", "description": "90分钟深度疗程。针对持续数月或数年的慢性病症：纤维肌痛、慢性疲劳综合征、临床抑郁、子宫内膜异位症、甲状腺功能障碍或神经性疼痛。"},
        6: {"name": "Sky Water - 高级共振", "description": "2小时高级疗程。针对多种同时存在的病理状况、确诊自身免疫疾病、外周神经病变、伴有躯体化的PTSD或复杂激素障碍。"},
        7: {"name": "Sky Water - 扩展波动", "description": "2.5小时尊享疗程。针对术后恢复、长新冠、自主神经功能紊乱、严重肾上腺功能不全或多器官受累。"},
        8: {"name": "Sky Water - 极致疗愈", "description": "3小时极致疗程。针对退行性疾病、严重神经系统症状、化疗后恢复或伴有躯体成分的严重精神障碍。"},
        9: {"name": "Sky Water - 全面蜕变", "description": "持续疗程直至稳定改善。针对需要持续干预的危重、终末期或高复杂度多系统慢性病症。"}
    }
}

def _keyword_score(symptoms: str) -> int:
    """Deterministic fallback level scorer based on keyword matching."""
    text = symptoms.lower()
    score = 3  # minimum for any real symptom

    # Severity intensifiers → bump to ≥ 4
    intensifiers = [
        "fuerte", "intenso", "intensa", "severo", "severa", "agudo", "aguda",
        "insoportable", "horrible", "terrible", "muy", "bastante", "mucho",
        "strong", "intense", "severe", "sharp", "unbearable", "horrible", "terrible", "very",
    ]
    if any(w in text for w in intensifiers):
        score = max(score, 4)

    # Chronic / long-term → bump to ≥ 5
    chronic_markers = [
        "crónico", "crónica", "años", "meses", "siempre", "desde niño", "desde pequeño",
        "toda la vida", "no se va", "no desaparece", "permanente", "constante",
        "chronic", "years", "months", "always", "lifelong", "won't go away", "constant", "permanent",
    ]
    if any(w in text for w in chronic_markers):
        score = max(score, 5)

    # High-severity conditions → level 5-6
    severe_conditions = [
        "fibromialgia", "fibromyalgia", "lupus", "artritis", "arthritis",
        "endometriosis", "tiroides", "thyroid", "autoinmune", "autoimmune",
        "depresión", "depression", "ansiedad severa", "severe anxiety",
        "fatiga crónica", "chronic fatigue", "insomnio crónico", "chronic insomnia",
        "gastritis", "colitis", "crohn", "intestino irritable", "irritable bowel",
    ]
    if any(w in text for w in severe_conditions):
        score = max(score, 5)

    # Very severe / complex → level 6-7
    very_severe = [
        "cáncer", "cancer", "tumor", "neuropatía", "neuropathy", "parkinson",
        "esclerosis", "sclerosis", "post-quirúrgico", "post-surgical", "quimioterapia",
        "chemotherapy", "covid largo", "long covid", "post-covid",
    ]
    if any(w in text for w in very_severe):
        score = max(score, 7)

    # Count distinct symptom mentions to escalate further
    symptom_words = [
        "dolor", "pain", "fatiga", "fatigue", "cabeza", "headache", "migraña", "migraine",
        "espalda", "back", "cuello", "neck", "estómago", "stomach", "tos", "cough",
        "insomnio", "insomnia", "ansiedad", "anxiety", "estrés", "stress",
        "náuseas", "nausea", "mareo", "dizziness", "articulaciones", "joints",
    ]
    symptom_count = sum(1 for w in symptom_words if w in text)
    if symptom_count >= 3:
        score = min(9, score + 1)
    if symptom_count >= 5:
        score = min(9, score + 1)

    return score


@api_router.post("/symptom-analyzer", response_model=SymptomAnalysisResponse)
async def analyze_symptoms(data: SymptomAnalysisRequest):
    session_id = data.session_id or str(uuid.uuid4())
    lang = data.language if data.language in ["es", "en", "it", "pt", "de", "fr", "ja", "ar", "ru", "zh"] else "en"
    
    # Language-specific instructions
    lang_instructions = {
        "es": "Responde SIEMPRE en español",
        "en": "ALWAYS respond in English",
        "it": "Rispondi SEMPRE in italiano",
        "pt": "Responda SEMPRE em português",
        "de": "Antworte IMMER auf Deutsch",
        "fr": "Réponds TOUJOURS en français",
        "ja": "必ず日本語で回答してください",
        "ar": "أجب دائماً باللغة العربية",
        "ru": "Отвечай ВСЕГДА на русском языке",
        "zh": "请始终用中文回答",
    }
    
    system_message = f"""You are a wellness consultant for Sky Water, a quantum energy healing platform.
{lang_instructions.get(lang, lang_instructions["en"])}.

Analyze the physical and emotional symptoms the user describes and recommend the most appropriate healing level (1-9).

HEALING LEVELS — physical symptom guide:
1. Very mild: slight tiredness after a busy week, minor seasonal sniffles, curiosity about wellness with no active symptoms.
2. Mild: occasional headaches, mild insomnia once in a while, low energy some days, mild digestive discomfort.
3. Moderate: frequent fatigue, recurring headaches, ongoing back or neck pain, regular sleep problems, mild anxiety.
4. Significant: strong persistent cough, intense or recurring migraines, notable joint pain, frequent anxiety or panic, hormonal imbalance, clear digestive issues such as gastritis or IBS.
5. Chronic: symptoms lasting months or years, fibromyalgia, chronic pain syndromes, autoimmune flare-ups, deep depression, chronic fatigue syndrome, endometriosis, thyroid issues.
6. Severe chronic: multiple simultaneous conditions, long-term autoimmune disease, neuropathy, serious hormonal disorders, trauma with physical manifestations.
7. Deep systemic: post-surgical recovery, long COVID symptoms, nervous system dysregulation, severe adrenal fatigue, multiple organ involvement.
8. Complex multi-system: degenerative conditions, serious neurological symptoms, post-chemotherapy recovery, severe mental health combined with physical illness.
9. Critical or palliative support: terminal or near-terminal diagnosis, extreme multi-system failure, profound spiritual crisis combined with severe physical illness.

MANDATORY RULES — follow exactly:
- Minimum recommended level for ANY real physical symptom: 3.
- If the user describes symptoms as "strong", "intense", "sharp", "severe", "unbearable", or similar intensifiers → minimum level 4.
- If symptoms are described as "chronic", "for years", "since childhood", "always", or "won't go away" → minimum level 5.
- Each additional distinct symptom or condition beyond the first → add +1 to the base level (max 9).
- NEVER recommend level 1 or 2 unless the user explicitly states they have NO symptoms and are just curious.
- When in doubt, round UP, not down. It is better to over-recommend than under-recommend.

OUTPUT FORMAT — respond ONLY with valid JSON, no other text before or after:
{{"analysis": "<empathetic analysis in the required language, 2-4 sentences>", "recommended_level": <integer 1-9>}}"""

    import json as _json

    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

    def _keyword_fallback_response(symptoms: str, lang: str) -> dict:
        """Return a language-specific empathetic message using keyword scoring."""
        level = _keyword_score(symptoms)
        messages = {
            "es": f"Basándonos en los síntomas que describes, hemos identificado el nivel de sanación más adecuado para ti. Tu cuerpo tiene la capacidad de recuperarse — necesitas la energía correcta para activar ese proceso.",
            "en": f"Based on the symptoms you describe, we have identified the most appropriate healing level for you. Your body has the capacity to recover — you need the right energy to activate that process.",
            "it": f"In base ai sintomi descritti, abbiamo identificato il livello di guarigione più adatto per te. Il tuo corpo ha la capacità di riprendersi — hai bisogno dell'energia giusta per attivare quel processo.",
            "pt": f"Com base nos sintomas descritos, identificamos o nível de cura mais adequado para você. Seu corpo tem a capacidade de se recuperar — você precisa da energia certa para ativar esse processo.",
            "de": f"Basierend auf den beschriebenen Symptomen haben wir die am besten geeignete Heilungsstufe für Sie identifiziert. Ihr Körper hat die Fähigkeit, sich zu erholen — Sie brauchen die richtige Energie, um diesen Prozess zu aktivieren.",
            "fr": f"Sur la base des symptômes décrits, nous avons identifié le niveau de guérison le plus approprié pour vous. Votre corps a la capacité de se rétablir — vous avez besoin de la bonne énergie pour activer ce processus.",
            "ja": f"説明された症状に基づいて、あなたに最適な癒しのレベルを特定しました。あなたの体には回復する力があります — そのプロセスを活性化するには正しいエネルギーが必要です。",
            "ar": f"استناداً إلى الأعراض التي وصفتها، حددنا مستوى الشفاء الأنسب لك. جسمك لديه القدرة على التعافي — تحتاج إلى الطاقة الصحيحة لتفعيل هذه العملية.",
            "ru": f"На основании описанных вами симптомов мы определили наиболее подходящий уровень исцеления для вас. Ваш организм способен восстановиться — вам нужна правильная энергия, чтобы активировать этот процесс.",
            "zh": f"根据您描述的症状，我们为您确定了最合适的疗愈级别。您的身体具有恢复的能力 — 您需要正确的能量来激活这个过程。",
        }
        return {
            "analysis": messages.get(lang, messages["en"]),
            "recommended_level": level,
        }

    recommended_level = 3
    analysis_text = ""

    # Try LiteLLM with OPENAI_API_KEY if available
    if OPENAI_API_KEY:
        try:
            import litellm
            import json as _json2
            litellm.api_key = OPENAI_API_KEY
            llm_response = await litellm.acompletion(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": data.symptoms},
                ],
                temperature=0.4,
                max_tokens=400,
            )
            raw = llm_response.choices[0].message.content or ""
            clean = raw.strip()
            if clean.startswith("```"):
                parts = clean.split("```")
                clean = parts[1] if len(parts) > 1 else clean
                if clean.startswith("json"):
                    clean = clean[4:]
            parsed = _json2.loads(clean.strip())
            analysis_text = parsed.get("analysis", raw)
            raw_level = int(parsed.get("recommended_level", 3))
            recommended_level = min(9, max(1, raw_level))
        except Exception as llm_err:
            logging.warning(f"LiteLLM failed, using keyword fallback: {llm_err}")
            fallback = _keyword_fallback_response(data.symptoms, lang)
            analysis_text = fallback["analysis"]
            recommended_level = fallback["recommended_level"]
    else:
        # No API key — use deterministic keyword fallback (always works, never 500)
        fallback = _keyword_fallback_response(data.symptoms, lang)
        analysis_text = fallback["analysis"]
        recommended_level = fallback["recommended_level"]

    level_info = LEVEL_INFO.get(lang, LEVEL_INFO["es"]).get(recommended_level, LEVEL_INFO["es"][3])

    return SymptomAnalysisResponse(
        analysis=analysis_text,
        recommended_level=recommended_level,
        level_name=level_info["name"],
        level_description=level_info["description"],
        session_id=session_id
    )

# ============== TESTIMONIALS ROUTES ==============

@api_router.get("/testimonials", response_model=List[Testimonial])
async def get_testimonials(page: int = 1, limit: int = 12, level: Optional[int] = None):
    skip = (page - 1) * limit
    query = {"$or": [{"status": "approved"}, {"status": {"$exists": False}}]}
    if level:
        query["level"] = level

    testimonials = await db.testimonials.find(query).skip(skip).limit(limit).to_list(limit)
    return [Testimonial(**t) for t in testimonials]

@api_router.get("/testimonials/count")
async def get_testimonials_count(level: Optional[int] = None):
    query = {"$or": [{"status": "approved"}, {"status": {"$exists": False}}]}
    if level:
        query["level"] = level
    count = await db.testimonials.count_documents(query)
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
    # Nombres más diversos y realistas
    first_names_male = ["Carlos", "Miguel", "Juan", "Pedro", "Roberto", "Fernando", "Diego", "Andrés", "Ricardo", "Jorge", "Antonio", "David", "Alejandro", "Luis", "Javier", "Manuel", "Pablo", "Sergio", "Raúl", "Alberto", "Tomás", "Víctor", "Enrique", "Francisco", "Daniel"]
    first_names_female = ["María", "Sofía", "Laura", "Ana", "Carmen", "Isabel", "Patricia", "Lucía", "Elena", "Claudia", "Rosa", "Valentina", "Gabriela", "Andrea", "Mariana", "Paula", "Daniela", "Carolina", "Fernanda", "Mónica", "Verónica", "Natalia", "Adriana", "Diana", "Silvia"]
    last_initials = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "Z"]
    
    locations = [
        "Ciudad de México", "Monterrey", "Guadalajara", "Puebla", "Cancún",
        "Madrid", "Barcelona", "Valencia", "Sevilla",
        "Buenos Aires", "Córdoba", "Rosario",
        "Bogotá", "Medellín", "Cartagena",
        "Lima", "Arequipa",
        "Santiago", "Valparaíso",
        "Miami", "Los Angeles", "Houston", "Nueva York",
        "São Paulo", "Rio de Janeiro"
    ]
    
    level_names = {
        1: "Sesión Introductoria",
        2: "Sesión Ligera",
        3: "Sesión Estándar", 
        4: "Sesión Extendida", 
        5: "Sesión Premium",
        6: "Sesión Deluxe", 
        7: "Sesión Intensiva", 
        8: "Sesión Completa",
        9: "Sesión Ilimitada"
    }
    
    # Testimonios humanizados, variados y enfocados en bienestar
    testimonial_texts = {
        1: [
            "Entré con curiosidad y salí convencida. La sesión introductoria me dio exactamente lo que necesitaba para entender de qué se trata esto.",
            "Sinceramente no esperaba mucho, pero la evaluación inicial fue muy acertada. Me sorprendió gratamente.",
            "Por el precio, valió completamente la pena. Me ayudó a identificar qué áreas de mi vida necesitan más atención.",
            "Mi hermana me lo recomendó y ahora entiendo por qué. Buen primer paso.",
            "Nunca había probado algo así. La sesión fue tranquila y me sentí escuchado/a.",
            "Tenía mis dudas pero decidí darle una oportunidad. No me arrepiento.",
        ],
        2: [
            "Llevaba semanas sin poder relajarme de verdad. Esta sesión me devolvió esa calma que tanto necesitaba.",
            "El estrés del trabajo me tenía agotada. Después de la sesión dormí como no lo hacía en meses.",
            "No soy de creer en estas cosas, pero algo cambió. Me siento más tranquilo.",
            "Mi esposa notó el cambio antes que yo. Dice que estoy más presente y menos irritable.",
            "Probé meditación, yoga, de todo... esto fue diferente. Algo hizo clic.",
            "Sesión corta pero efectiva. Justo lo que necesitaba en medio de una semana caótica.",
            "Me lo recomendó un amigo escéptico como yo. Ahora ambos somos clientes regulares jaja",
        ],
        3: [
            "Tres sesiones y ya noto una diferencia real en cómo manejo el estrés diario.",
            "El insomnio era mi compañero de años. Ahora duermo profundamente casi todas las noches.",
            "Me ayudó a soltar tensiones que ni sabía que cargaba. Literalmente me siento más ligera.",
            "Después de la sesión tuve una claridad mental que hacía tiempo no experimentaba.",
            "Empecé por curiosidad, sigo porque realmente funciona para mí.",
            "No sé explicar exactamente qué pasa, pero termino cada sesión sintiéndome renovada.",
        ],
        4: [
            "La sesión extendida vale cada peso. Salí como nueva después de meses de sentirme agotada.",
            "Increíble cómo una hora puede cambiar tu perspectiva. Me sentí escuchada y atendida.",
            "Venía arrastrando el cansancio de todo el año. Una sesión y ya respiro diferente.",
            "Mi terapeuta me sugirió complementar con algo así. Gran decisión.",
            "El tiempo pasa volando durante la sesión. Cuando termina no quieres que acabe.",
            "Después de esta sesión tomé decisiones que venía postergando. Claridad total.",
        ],
        5: [
            "Cinco meses viniendo y mi calidad de vida mejoró notablemente. Mi familia también lo nota.",
            "Invertir en bienestar no es un lujo, es necesidad. Esta sesión me lo confirmó.",
            "Antes vivía estresada 24/7. Ahora tengo herramientas para manejar mejor los días difíciles.",
            "La sesión premium es otro nivel. Profunda, transformadora, vale completamente la pena.",
            "Mi médico me preguntó qué estaba haciendo diferente porque mis niveles de estrés bajaron.",
            "No cambié nada más en mi rutina. Solo estas sesiones. Y la diferencia es notable.",
        ],
        6: [
            "Dos horas que se sienten como un retiro de fin de semana. Desconectas completamente.",
            "Llegué agotada física y emocionalmente. Salí sintiéndome como después de unas vacaciones.",
            "Esta sesión me ayudó a procesar cosas que llevaba guardando mucho tiempo.",
            "Mi regalo de cumpleaños para mí misma. Mejor decisión del año.",
            "Después de esta sesión renuncié a un trabajo que me hacía infeliz. Gracias por la claridad.",
        ],
        7: [
            "La sesión intensiva es para quienes realmente quieren un cambio profundo. No es para curiosos.",
            "Meses de terapia tradicional no lograron lo que logré en estas sesiones. Complemento perfecto.",
            "Llegué siendo una persona, salí siendo otra. Suena exagerado pero así lo sentí.",
            "Mi esposo no entendía por qué seguía viniendo. Ahora él también tiene sus citas.",
            "Esta sesión me ayudó a reconectar conmigo misma después de años de solo existir.",
        ],
        8: [
            "La sesión completa es una inversión en ti mismo que paga dividendos toda la vida.",
            "Tres horas de trabajo profundo. Terminé agotada pero liberada de tanto peso.",
            "Después de esta sesión perdoné cosas que cargaba desde la infancia. Transformador.",
            "Mi mejor amiga y yo lo hicimos juntas. Fortalecimos nuestra conexión además de sentirnos increíbles.",
        ],
        9: [
            "El paquete ilimitado cambió mi vida. No exagero. Soy otra persona.",
            "Cuando encuentras algo que funciona, inviertes en ello. Simple.",
            "Mi familia pensaba que estaba loca por gastar en esto. Ahora todos quieren probarlo.",
        ]
    }
    
    # Ratings más realistas (no todos 5 estrellas)
    rating_weights = [4, 4, 4, 5, 5, 5, 5, 5, 5, 5]  # Mayoría 5, algunos 4

    months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    years = ["2024", "2025"]

    testimonials = []
    level_counts = {1: 45, 2: 52, 3: 38, 4: 41, 5: 35, 6: 28, 7: 19, 8: 12, 9: 6}

    used_text_combos = set()

    for level, count in level_counts.items():
        texts = testimonial_texts[level]
        # Shuffle texts first, then cycle — ensures earliest entries have most variety
        shuffled_texts = texts[:]
        random.shuffle(shuffled_texts)
        text_cycle = (shuffled_texts * ((count // len(shuffled_texts)) + 2))
        random.shuffle(text_cycle)

        text_index = 0
        for i in range(count):
            while True:
                is_female = random.random() > 0.45
                name = random.choice(first_names_female if is_female else first_names_male)
                initial = random.choice(last_initials)
                location = random.choice(locations)
                # Pick next text that hasn't been used with this name+location combo
                text = text_cycle[text_index % len(text_cycle)]
                text_index += 1

                combo = f"{name}{initial}{location}{text[:30]}"
                if combo not in used_text_combos:
                    used_text_combos.add(combo)
                    break

            month = random.choice(months)
            year = random.choice(years)

            testimonials.append(Testimonial(
                name=f"{name} {initial}.",
                rating=random.choice(rating_weights),
                location=location,
                level=level,
                level_name=level_names[level],
                text=text,
                date=f"{month} {year}"
            ))

    random.shuffle(testimonials)
    return testimonials

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
    google_event_id: Optional[str] = None  # Google Calendar event ID (set after booking)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AppointmentCreate(BaseModel):
    date: str
    time: str
    order_id: str
    patient_email: str
    patient_name: str
    product_name: str

# Appointments are persisted in MongoDB (db.appointments collection)

# ============== TELEGRAM INSTANT NOTIFICATIONS ==============

async def send_telegram_notification(apt_data: dict, product_name: str, order: dict = None):
    """Send an instant Telegram message when a new appointment is booked.

    Fires immediately after MongoDB insert — independent of email/Calendar.
    Fails silently so it never blocks the booking flow.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — skipping instant notification")
        return

    try:
        patient_data = order.get("patient_data", {}) if order else {}
        def _g(k): return (patient_data.get(k) or "").strip()
        full_name = " ".join(x for x in [_g("first_name"), _g("second_name"), _g("first_lastname"), _g("second_lastname")] if x) or apt_data.get("patient_name", "")
        symptoms = patient_data.get("symptoms", "No especificado")
        city = patient_data.get("city", "")
        country = patient_data.get("country", "")
        location_str = ", ".join(x for x in [_g("city"), _g("state"), _g("country")] if x) or "No especificado"
        address_str = ", ".join(x for x in [_g("address"), _g("postal_code")] if x) or "No especificado"
        birth_date = _g("birth_date"); rfc = _g("rfc"); email_pd = _g("email")

        # Format date/time nicely
        import pytz
        mexico_tz = pytz.timezone("America/Mexico_City")
        try:
            dt = datetime.strptime(f"{apt_data['date']} {apt_data['time']}", "%Y-%m-%d %H:%M")
            dt_local = mexico_tz.localize(dt)
            weekdays_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            weekday = weekdays_es[dt_local.weekday()]
            date_fmt = f"{weekday} {dt_local.day} de {dt_local.strftime('%B')} · {apt_data['time']} hrs"
        except Exception:
            date_fmt = f"{apt_data['date']} · {apt_data['time']} hrs"

        # Síntomas completos (cap a 3000 por límite de Telegram ~4096)
        symptoms_short = symptoms[:3000] + "..." if len(symptoms) > 3000 else symptoms

        message = (
            f"🌊 *NUEVA CITA SKY WATER*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Paciente:* {full_name}\n"
            f"📧 *Email:* {apt_data['patient_email'] or email_pd}\n"
            + (f"🎂 *Nacimiento:* {birth_date}\n" if birth_date else "")
            + f"💊 *Servicio:* {product_name}\n"
            f"📅 *Fecha:* {date_fmt}\n"
            f"📍 *Ubicación:* {location_str}\n"
            f"🏠 *Dirección:* {address_str}\n"
            + (f"🏛️ *RFC:* {rfc}\n" if rfc else "")
            + f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🩺 *Síntomas / lo que reportó:*\n{symptoms_short}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🧾 Orden: `{apt_data['order_id']}`"
        )

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_notification": False,  # Always ring with sound
        }

        async with httpx.AsyncClient() as client_http:
            resp = await client_http.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"✅ Telegram notification sent for {apt_data['patient_name']}")
            else:
                logger.error(f"Telegram API error {resp.status_code}: {resp.text}")

    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")


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
                        <li>Evita distracciones durante los 45 minutos de tu sesión</li>
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

def generate_admin_notification_email(apt_data: dict, product_name: str, week_appointments: list = None):
    """Generate HTML email for admin notification"""
    week_calendar = []
    for apt in (week_appointments or []):
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

# ============== GOOGLE CALENDAR HELPERS ==============

def get_google_calendar_service():
    """Build Google Calendar API service using stored OAuth2 refresh token."""
    if not GOOGLE_CALENDAR_AVAILABLE:
        return None
    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN]):
        logger.warning("Google Calendar credentials not configured — skipping calendar sync")
        return None
    try:
        creds = Credentials(
            token=None,
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/calendar.events"],
        )
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        logger.error(f"Failed to build Google Calendar service: {e}")
        return None


async def create_google_calendar_event(apt_data: dict, product_name: str, order: dict = None) -> Optional[str]:
    """Create a Google Calendar event for a confirmed appointment.

    Returns the Google event ID, or None on failure.
    Booking is NOT cancelled if this fails — it degrades gracefully.
    """
    service = get_google_calendar_service()
    if not service:
        return None

    try:
        mexico_tz = pytz.timezone("America/Mexico_City")
        date_str = apt_data["date"]   # "2026-05-04"
        time_str = apt_data["time"]   # "11:00"
        start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        start_dt = mexico_tz.localize(start_dt)
        end_dt = start_dt + timedelta(minutes=45)

        # Build rich description with all patient info + symptoms
        patient_data = order.get("patient_data", {}) if order else {}
        def _g(k): return (patient_data.get(k) or "").strip()
        symptoms = patient_data.get("symptoms", "No especificado")
        birth_date = _g("birth_date")
        country = _g("country"); state = _g("state"); city = _g("city")
        address = _g("address"); postal_code = _g("postal_code")
        rfc = _g("rfc")
        full_name = " ".join(x for x in [_g("first_name"), _g("second_name"), _g("first_lastname"), _g("second_lastname")] if x) or apt_data.get("patient_name", "")

        description_lines = [
            f"👤 Paciente: {full_name}",
            f"📧 Email: {apt_data['patient_email'] or _g('email')}",
            f"🌊 Servicio: {product_name}",
            f"🧾 Orden: {apt_data['order_id']}",
            "",
            "📍 Ubicación del paciente:",
            f"   {', '.join(x for x in [city, state, country] if x) or 'No especificado'}",
            f"🏠 Dirección: {', '.join(x for x in [address, postal_code] if x) or 'No especificado'}",
        ]
        if birth_date:
            description_lines.append(f"🎂 Fecha de nacimiento: {birth_date}")
        if rfc:
            description_lines.append(f"🏛️ RFC: {rfc}")
        description_lines += [
            "",
            "🩺 Síntomas / lo que reportó el paciente:",
            symptoms,
        ]

        event_body = {
            "summary": f"🌊 Cita Sky Water — {apt_data['patient_name']} — {product_name}",
            "description": "\n".join(description_lines),
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "America/Mexico_City",
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "America/Mexico_City",
            },
            "colorId": "7",  # Peacock (cyan/teal) in Google Calendar
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 30},
                    {"method": "email", "minutes": 30},
                ],
            },
        }

        event = service.events().insert(
            calendarId=GOOGLE_CALENDAR_ID,
            body=event_body,
        ).execute()

        event_id = event.get("id")
        logger.info(f"✅ Google Calendar event created: {event_id} for {apt_data['patient_name']} on {date_str} {time_str}")
        return event_id

    except Exception as e:
        logger.error(f"Google Calendar event creation failed: {e}")
        return None


# ============== APPOINTMENT SLOTS ==============

@api_router.get("/appointments/available-slots")
async def get_available_slots(date: str = None):
    """Return all appointment slots (available AND booked) for next 14 weekdays.

    Schedule: Monday–Friday
    • Morning  : 11:00 · 11:45 · 12:30 · 13:15  (lunch break 14:00–16:00)
    • Afternoon: 16:00 · 16:45 · 17:15
    • Slot duration: 45 minutes  •  Max 1 booking per slot
    """
    mexico_tz = pytz.timezone('America/Mexico_City')
    now_local = datetime.now(mexico_tz)
    today = now_local.date()

    # 45-minute slots — morning before lunch, afternoon after lunch
    SLOT_TIMES = ["11:00", "11:45", "12:30", "13:15", "16:00", "16:45", "17:15"]

    slots = []
    dates_to_check = []

    if date:
        try:
            dates_to_check = [datetime.strptime(date, "%Y-%m-%d").date()]
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usa YYYY-MM-DD")
    else:
        # Collect the next 14 weekdays
        count, i = 0, 0
        while count < 14:
            check_date = today + timedelta(days=i)
            i += 1
            if check_date.weekday() < 5:  # Monday=0 … Friday=4
                dates_to_check.append(check_date)
                count += 1

    for check_date in dates_to_check:
        if check_date.weekday() >= 5:
            continue

        date_str = check_date.strftime("%Y-%m-%d")
        for time_slot in SLOT_TIMES:
            # Skip slots whose start time has already passed (only for today)
            if check_date == today:
                slot_hour, slot_min = map(int, time_slot.split(":"))
                if now_local.hour > slot_hour or (
                    now_local.hour == slot_hour and now_local.minute >= slot_min
                ):
                    continue

            existing = await db.appointments.count_documents(
                {"date": date_str, "time": time_slot, "status": {"$ne": "cancelled"}}
            )

            # Return all slots (available + booked) so the frontend can show occupied cards
            slots.append({
                "date": date_str,
                "time": time_slot,
                "available": existing == 0,
                "available_spots": 1 if existing == 0 else 0,
            })

    return {"slots": slots}

@api_router.post("/appointments/book")
async def book_appointment(appointment: AppointmentCreate):
    """Book an appointment slot — requires confirmed payment.

    One appointment per slot (strict), one appointment per order.
    Creates a Google Calendar event on the admin's calendar automatically.
    """

    # 1. Verify the order exists and is paid
    order = await db.orders.find_one({"id": appointment.order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if order.get("payment_status") != "completed":
        raise HTTPException(
            status_code=403,
            detail="El pago no ha sido confirmado. Completa el pago antes de agendar tu cita."
        )

    # 2. Prevent double-booking the same order
    already_booked = await db.appointments.find_one(
        {"order_id": appointment.order_id, "status": {"$ne": "cancelled"}}
    )
    if already_booked:
        raise HTTPException(status_code=400, detail="Esta orden ya tiene una cita agendada")

    # 3. Check slot availability (strict: max 1 appointment per 45-min slot)
    existing = await db.appointments.count_documents(
        {"date": appointment.date, "time": appointment.time, "status": {"$ne": "cancelled"}}
    )
    if existing >= 1:
        raise HTTPException(
            status_code=400,
            detail="Este horario ya está ocupado. Por favor elige otro horario disponible."
        )

    apt_data = {
        "id": str(uuid.uuid4()),
        "date": appointment.date,
        "time": appointment.time,
        "patient_email": appointment.patient_email,
        "patient_name": appointment.patient_name,
        "order_id": appointment.order_id,
        "product_name": appointment.product_name,
        "status": "confirmed",
        "google_event_id": None,
        "created_at": datetime.utcnow().isoformat()
    }

    # 4. Persist in MongoDB
    await db.appointments.insert_one(apt_data)

    # 4b. Send instant Telegram notification (fires immediately, non-blocking)
    await send_telegram_notification(apt_data, appointment.product_name, order)

    # 4c. Create Google Calendar event (non-blocking — booking succeeds even if this fails)
    google_event_id = await create_google_calendar_event(apt_data, appointment.product_name, order)
    if google_event_id:
        await db.appointments.update_one(
            {"id": apt_data["id"]},
            {"$set": {"google_event_id": google_event_id}}
        )
        apt_data["google_event_id"] = google_event_id

    # 5. Send confirmation email to patient
    patient_email_html = generate_appointment_confirmation_email(apt_data, appointment.product_name)
    send_appointment_email(
        appointment.patient_email,
        f"✅ Cita Confirmada - Sky Water - {appointment.date}",
        patient_email_html
    )

    # 6. Send notification email to admin (include upcoming appointments for context)
    week_apts = await db.appointments.find(
        {"status": {"$ne": "cancelled"}}, {"_id": 0}
    ).sort("date", 1).limit(20).to_list(length=20)
    admin_email_html = generate_admin_notification_email(apt_data, appointment.product_name, week_apts)
    send_appointment_email(
        ADMIN_EMAIL,
        f"🔔 Nueva Cita: {appointment.patient_name} — {appointment.date} {appointment.time}",
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
    cursor = db.appointments.find({"order_id": order_id}, {"_id": 0})
    user_appointments = await cursor.to_list(length=20)
    return {"appointments": user_appointments}

# ============== HOW IT WORKS - SCIENTIFIC BASIS ==============

@api_router.get("/how-it-works")
async def get_how_it_works(lang: str = "es"):
    """Get the scientific basis and explanation of energy healing"""
    
    if lang == "en":
        return {
            "title": "How Does Sky Water Work?",
            "subtitle": "The Science Behind Energy Healing",
            "introduction": """
Sky Water uses principles of distance energy healing, a practice supported by recent scientific research. 
Our method is based on the transmission of quantum bioenergy that operates independently of physical distance, 
allowing a direct energetic connection between the healer and the recipient.
            """,
            "scientific_studies": [
                {
                    "title": "Controlled Clinical Study on Distance Energy Healing",
                    "source": "National Institutes of Health (NIH) - PubMed Central",
                    "year": "2024",
                    "reference": "PMC11392496",
                    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11392496/",
                    "summary": "A randomized, double-blind, placebo-controlled clinical trial (n=114 adults) demonstrated that distance energy healing significantly improved psychological symptoms such as fatigue, anxiety, depression, sleep problems, and stress (p<0.0001). No adverse effects were reported.",
                    "key_findings": [
                        "Significant improvement in all symptoms evaluated",
                        "Results superior to placebo and control groups",
                        "No adverse effects reported",
                        "Improvement in overall quality of life"
                    ]
                },
                {
                    "title": "Comprehensive Review of 353 Clinical Studies on Biofield Therapy",
                    "source": "PubMed - Journal of Integrative and Complementary Medicine",
                    "year": "2025",
                    "reference": "PMID: 39854162",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/39854162/",
                    "summary": "An exhaustive review analyzing 353 peer-reviewed clinical studies (255 randomized controlled trials) on biofield therapies. Nearly half (172 studies) reported positive results in various health conditions.",
                    "key_findings": [
                        "353 clinical studies analyzed",
                        "255 randomized controlled trials (RCTs)",
                        "172 studies with positive results",
                        "Demonstrated effectiveness in pain, fatigue, anxiety, and more"
                    ]
                },
                {
                    "title": "Quantum Mechanisms in Bioenergy Therapy",
                    "source": "Healing Warriors Program - Review 2024",
                    "year": "2024",
                    "reference": "Narrative Review",
                    "url": "https://www.healingwarriorsprogram.org/",
                    "summary": "This narrative review proposes quantum mechanisms such as entanglement to explain the effects of biofield therapies. It documents preclinical and clinical evidence showing effectiveness in pain, cancer-related fatigue, stress, and mental health disorders.",
                    "key_findings": [
                        "Proposal of quantum mechanisms (entanglement)",
                        "Effectiveness in multiple conditions",
                        "Solid theoretical basis for distance healing",
                        "Integration of quantum physics and biology"
                    ]
                }
            ],
            "our_method": {
                "title": "The Sky Water Method",
                "steps": [
                    {
                        "step": 1,
                        "title": "Initial Connection",
                        "description": "We use your personal data (full name, location, date of birth) to establish a unique and personalized energetic connection."
                    },
                    {
                        "step": 2,
                        "title": "Energy Analysis",
                        "description": "The detailed description of your symptoms allows us to identify the specific energy blockages that require attention."
                    },
                    {
                        "step": 3,
                        "title": "Bioenergy Transmission",
                        "description": "During your scheduled appointment, we channel healing energy specifically calibrated for your condition, using quantum resonance principles."
                    },
                    {
                        "step": 4,
                        "title": "Integration",
                        "description": "Your body integrates the received energy. It is important to stay hydrated and in a receptive state during and after the session."
                    }
                ]
            },
            "preparation_instructions": {
                "title": "Preparing for Your Session",
                "water_formula": "Multiply your weight in kg by 35ml to get your recommended daily water intake.",
                "special_water": "Drink at least 2 glasses of water with lemon and a pinch of unrefined coarse salt (without iodine or fluoride) per day. If you don't have unrefined salt, you can use regular table salt occasionally.",
                "during_session": "During the 30-minute session, stay in a comfortable place (home, work, anywhere) in a relaxed position.",
                "tips": [
                    "Be in a quiet environment",
                    "Comfortable position (sitting or lying down)",
                    "Keep an open and receptive mind",
                    "Avoid distractions during the session",
                    "Drink water before and after the session"
                ]
            },
            "disclaimer": "Sky Water is a complementary energy healing service. It does not replace professional medical diagnosis, treatment, or advice."
        }
    
    # Default: Spanish
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

# ============== META WEBHOOK ==============
META_WEBHOOK_VERIFY_TOKEN = "skywater_webhook_2025"

@api_router.get("/webhook")
async def meta_webhook_verify(request: Request):
    """Meta webhook verification endpoint"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == META_WEBHOOK_VERIFY_TOKEN:
        return int(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")

@api_router.post("/webhook")
async def meta_webhook_receive(request: Request):
    """Meta webhook event receiver"""
    try:
        data = await request.json()
        logging.info(f"Meta webhook event received: {data}")
    except Exception as e:
        logging.error(f"Meta webhook error: {e}")
    return {"status": "ok"}

# ============== REFERRAL SYSTEM ==============

class GenerateReferralRequest(BaseModel):
    email: str

class ApplyReferralRequest(BaseModel):
    referral_code: str
    buyer_email: str
    order_id: str  # obligatorio: el referido SOLO se registra sobre una orden pagada y verificada
    purchase_level: Optional[int] = None  # ignorado (legacy)

# Reward thresholds
REFERRAL_REWARDS = [
    {"required": 2, "reward_type": "discount", "description": "Cupón 20% descuento en nivel 1 o 2"},
    {"required": 3, "reward_type": "free_session", "description": "Sesión nivel 3 completamente gratis"},
]

def _generate_code() -> str:
    import random, string
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"SKY-{suffix}"


def _generate_coupon_code() -> str:
    import random, string
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"SWC-{suffix}"


# Descuento para el COMPRADOR que usa un código de referido válido (promesa del mensaje de compartir).
REFERRAL_BUYER_DISCOUNT_PCT = 10


async def register_referral_atomic(referral_code, buyer_email):
    """Registra un referido de forma ATÓMICA y anti-fraude. Nunca lanza (uso seguro desde el webhook).

    - $addToSet en una sola op: dedup por email + bloqueo de auto-referido sin race.
    - Desbloqueo de recompensas idempotente (guard atómico evita duplicados bajo concurrencia).
    Llamar SOLO sobre un pago verificado (webhook/confirmación de orden pagada).
    """
    if not referral_code:
        return None
    code = referral_code.upper().strip()
    buyer = (buyer_email or "").lower().strip()
    if not buyer:
        return {"ok": False, "reason": "no_buyer"}

    doc = await db.referrals.find_one({"code": code})
    if not doc:
        return {"ok": False, "reason": "code_not_found"}
    if buyer == doc["owner_email"]:
        return {"ok": False, "reason": "self_referral"}

    # Paso A — añadir comprador atómicamente (dedup + anti auto-referido en una sola op)
    add = await db.referrals.update_one(
        {"code": code, "owner_email": {"$ne": buyer}, "referred_emails": {"$ne": buyer}},
        {"$addToSet": {"referred_emails": buyer}},
    )
    if add.modified_count == 0:
        fresh = await db.referrals.find_one({"code": code})
        return {"ok": False, "reason": "already_counted", "referral_count": len(fresh.get("referred_emails", []))}

    # Paso B — desbloquear recompensas pendientes (idempotente, guard atómico)
    fresh = await db.referrals.find_one({"code": code})
    new_count = len(fresh.get("referred_emails", []))
    unlocked_now = []
    for r in REFERRAL_REWARDS:
        if new_count >= r["required"]:
            reward_doc = {
                "required": r["required"],
                "reward_type": r["reward_type"],
                "description": r["description"],
                "unlocked_at": datetime.utcnow().isoformat(),
                "redeemed": False,
            }
            res = await db.referrals.update_one(
                {"code": code, "rewards_unlocked.required": {"$ne": r["required"]}},
                {"$push": {"rewards_unlocked": reward_doc}},
            )
            if res.modified_count:
                unlocked_now.append(reward_doc)

    final = await db.referrals.find_one({"code": code})
    return {"ok": True, "referral_count": new_count,
            "rewards_unlocked": final.get("rewards_unlocked", []), "new_rewards": unlocked_now}


async def resolve_discount_code(raw_code, buyer_email):
    """Resuelve un código ingresado en el checkout: cupón canjeado o código de referido.

    Devuelve {kind, discount_pct, coupon_code, referral_code} (discount_pct=0 si no aplica).
    - Cupón de recompensa (db.coupons, no usado) → su discount_pct (ej. 20%).
    - Código de referido válido (no auto-referido) → REFERRAL_BUYER_DISCOUNT_PCT (10%).
    El descuento se calcula SIEMPRE en el servidor; nunca se confía en el cliente.
    """
    out = {"kind": None, "discount_pct": 0, "coupon_code": None, "referral_code": None}
    if not raw_code:
        return out
    code = raw_code.upper().strip()
    buyer = (buyer_email or "").lower().strip()

    coupon = await db.coupons.find_one({"code": code, "used": False})
    if coupon:
        pct = int(coupon.get("discount_pct", 0) or 0)
        # Cupones 100% (sesión gratis) NO pasan por MercadoPago ($0 inválido) -> se canjean aparte.
        if 0 < pct < 100:
            out.update(kind="coupon", discount_pct=pct, coupon_code=code)
        return out

    ref = await db.referrals.find_one({"code": code})
    if ref and ref.get("owner_email") != buyer:
        out.update(kind="referral", discount_pct=REFERRAL_BUYER_DISCOUNT_PCT, referral_code=code)
    return out

@api_router.post("/referral/generate")
async def generate_referral_code(body: GenerateReferralRequest):
    """Generate (or return existing) referral code for a user email."""
    email = body.email.lower().strip()
    existing = await db.referrals.find_one({"owner_email": email})
    if existing:
        return {
            "code": existing["code"],
            "owner_email": email,
            "referral_count": len(existing.get("referred_emails", [])),
            "rewards_unlocked": existing.get("rewards_unlocked", []),
        }

    # Generate unique code
    for _ in range(10):
        code = _generate_code()
        clash = await db.referrals.find_one({"code": code})
        if not clash:
            break

    doc = {
        "code": code,
        "owner_email": email,
        "referred_emails": [],
        "rewards_unlocked": [],
        "created_at": datetime.utcnow().isoformat(),
    }
    await db.referrals.insert_one(doc)
    return {"code": code, "owner_email": email, "referral_count": 0, "rewards_unlocked": []}

@api_router.get("/referral/{code}")
async def validate_referral_code(code: str):
    """Validate a referral code and return its stats."""
    doc = await db.referrals.find_one({"code": code.upper()})
    if not doc:
        raise HTTPException(status_code=404, detail="Código de referido no encontrado")
    count = len(doc.get("referred_emails", []))
    # NO exponer owner_email: endpoint público sin auth (evita fuga de PII).
    return {
        "valid": True,
        "code": doc["code"],
        "referral_count": count,
    }

@api_router.post("/referral/apply")
async def apply_referral_code(body: ApplyReferralRequest):
    """Registrar un referido SOBRE UNA ORDEN PAGADA Y VERIFICADA (anti-farmeo).

    Verifica que la orden exista, esté pagada y pertenezca al comprador antes de contar.
    Para MercadoPago el registro ya ocurre en el webhook; esta ruta cubre USDT/compat.
    Idempotente: marca la orden para no recontar.
    """
    code = body.referral_code.upper().strip()
    buyer = body.buyer_email.lower().strip()

    order = await db.orders.find_one({"id": body.order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if order.get("payment_status") not in ("completed", "approved"):
        raise HTTPException(status_code=400, detail="La orden no está pagada")
    order_email = (order.get("patient_data") or {}).get("email", "").lower().strip()
    if order_email != buyer:
        raise HTTPException(status_code=400, detail="El comprador no coincide con la orden")
    if order.get("referral_applied"):
        return {"message": "Este referido ya fue contabilizado"}

    res = await register_referral_atomic(code, buyer)
    await db.orders.update_one({"id": body.order_id}, {"$set": {"referral_applied": True, "referral_code": code}})

    if not res or res.get("reason") == "code_not_found":
        raise HTTPException(status_code=404, detail="Código de referido no válido")
    if res.get("reason") == "self_referral":
        raise HTTPException(status_code=400, detail="No puedes usar tu propio código de referido")
    if res.get("reason") == "already_counted":
        return {"message": "Este email ya fue contabilizado", "referral_count": res.get("referral_count", 0)}

    return {
        "message": "Referido registrado correctamente",
        "referral_count": res["referral_count"],
        "rewards_unlocked": res["rewards_unlocked"],
        "new_reward_unlocked": len(res["new_rewards"]) > 0,
    }

@api_router.get("/referral/rewards/{email}")
async def get_referral_rewards(email: str):
    """Return referral stats and rewards for a user."""
    email = email.lower().strip()
    doc = await db.referrals.find_one({"owner_email": email})
    if not doc:
        return {"has_code": False, "code": None, "referral_count": 0, "rewards_unlocked": [], "next_reward": REFERRAL_REWARDS[0]}

    count = len(doc.get("referred_emails", []))
    unlocked = doc.get("rewards_unlocked", [])
    unlocked_required = {r["required"] for r in unlocked}
    next_reward = next((r for r in REFERRAL_REWARDS if r["required"] not in unlocked_required), None)

    return {
        "has_code": True,
        "code": doc["code"],
        "referral_count": count,
        "rewards_unlocked": unlocked,
        "next_reward": next_reward,
    }

# ============== TESTIMONIALS SUBMIT ==============

@api_router.post("/testimonials/submit")
async def submit_testimonial(body: TestimonialSubmit):
    """User-submitted testimonial — goes to pending moderation."""
    # Dedup: one per order_id
    existing = await db.testimonials.find_one({"order_id": body.order_id, "source": "user"})
    if existing:
        raise HTTPException(status_code=400, detail="Ya enviaste un testimonio para esta sesión")

    # Validate order exists and is paid
    order = await db.orders.find_one({"id": body.order_id})
    if not order or order.get("payment_status") != "completed":
        raise HTTPException(status_code=400, detail="Orden no válida o no pagada")

    doc = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "rating": min(5, max(1, body.rating)),
        "location": body.country,
        "level": body.level,
        "level_name": body.level_name,
        "text": body.text,
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "verified": False,
        "status": "pending",
        "email": body.email,
        "order_id": body.order_id,
        "submitted_at": datetime.utcnow().isoformat(),
        "moderated_at": None,
        "source": "user",
    }
    await db.testimonials.insert_one(doc)
    return {"success": True, "id": doc["id"], "message": "¡Gracias! Tu testimonio será revisado pronto."}


# ============== REFERRAL REDEEM ==============

@api_router.post("/referral/redeem")
async def redeem_referral_reward(body: RedeemRewardRequest):
    """Canjear una recompensa: genera un CUPÓN real (db.coupons) que el checkout honra.

    Atómico: marca la recompensa canjeada en una sola op (evita doble canje bajo concurrencia).
    Cupón 20% (descuento) → aplicable directo en el checkout.
    Cupón 100% (sesión gratis) → se entrega el código pero se canjea con soporte ($0 no pasa por MercadoPago).
    """
    email = body.email.lower().strip()
    doc = await db.referrals.find_one({"owner_email": email})
    if not doc:
        raise HTTPException(status_code=404, detail="No se encontró código de referido para este email")

    rewards = doc.get("rewards_unlocked", [])
    if body.reward_index < 0 or body.reward_index >= len(rewards):
        raise HTTPException(status_code=400, detail="Recompensa no encontrada")

    reward = rewards[body.reward_index]
    if reward.get("redeemed", False):
        raise HTTPException(status_code=400, detail="Esta recompensa ya fue canjeada")

    reward_type = reward.get("reward_type", "discount")
    required = reward.get("required")
    discount_percent = 100 if reward_type == "free_session" else 20

    # Cupón único
    for _ in range(10):
        coupon_code = _generate_coupon_code()
        if not await db.coupons.find_one({"code": coupon_code}):
            break

    # Marcar canjeada de forma ATÓMICA (guard: aún no canjeada)
    upd = await db.referrals.update_one(
        {"owner_email": email,
         "rewards_unlocked": {"$elemMatch": {"required": required, "redeemed": {"$ne": True}}}},
        {"$set": {
            "rewards_unlocked.$[r].redeemed": True,
            "rewards_unlocked.$[r].redeemed_at": datetime.utcnow().isoformat(),
            "rewards_unlocked.$[r].coupon_code": coupon_code,
        }},
        array_filters=[{"r.required": required}],
    )
    if upd.modified_count == 0:
        raise HTTPException(status_code=400, detail="Esta recompensa ya fue canjeada")

    await db.coupons.insert_one({
        "code": coupon_code,
        "owner_email": email,
        "discount_pct": discount_percent,
        "reward_type": reward_type,
        "reward_required": required,
        "used": False,
        "created_at": datetime.utcnow().isoformat(),
    })

    return {
        "success": True,
        "coupon_code": coupon_code,
        "reward_type": reward_type,
        "discount_percent": discount_percent,
        "free_session": reward_type == "free_session",
        "description": reward.get("description", ""),
    }


# ============== PUSH TOKENS ==============

@api_router.post("/push-token")
async def register_push_token(body: PushTokenRegister):
    """Store or update an Expo push token for a user."""
    if not body.token.startswith("ExponentPushToken["):
        return {"success": False, "message": "Invalid token format"}

    await db.push_tokens.update_one(
        {"email": body.email.lower().strip()},
        {"$set": {
            "email": body.email.lower().strip(),
            "token": body.token,
            "platform": body.platform,
            "updated_at": datetime.utcnow().isoformat(),
        }, "$setOnInsert": {"created_at": datetime.utcnow().isoformat()}},
        upsert=True,
    )
    return {"success": True}


async def send_push_notification(token: str, title: str, body: str, data: dict = None) -> bool:
    """Send a push notification via Expo Push API."""
    try:
        payload = {"to": token, "title": title, "body": body, "sound": "default"}
        if data:
            payload["data"] = data
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://exp.host/--/api/v2/push/send",
                json=payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=10,
            )
        return r.status_code == 200
    except Exception as e:
        logging.warning(f"Push notification failed: {e}")
        return False


async def send_pending_reminders():
    """Find appointments starting within 45-75 min and send reminder push."""
    try:
        tz = pytz.timezone("America/Mexico_City")
        now = datetime.now(tz)
        target_start = now + timedelta(minutes=45)
        target_end = now + timedelta(minutes=75)
        target_date = now.strftime("%Y-%m-%d")

        appointments = await db.appointments.find({
            "date": target_date,
            "status": {"$ne": "cancelled"},
            "reminder_sent": {"$ne": True},
        }).to_list(50)

        for apt in appointments:
            apt_time_str = apt.get("time", "")
            if not apt_time_str:
                continue
            try:
                apt_hour, apt_min = map(int, apt_time_str.split(":"))
                apt_dt = tz.localize(now.replace(hour=apt_hour, minute=apt_min, second=0))
                if target_start <= apt_dt <= target_end:
                    email = apt.get("patient_email", "")
                    token_doc = await db.push_tokens.find_one({"email": email})
                    if token_doc:
                        await send_push_notification(
                            token=token_doc["token"],
                            title="Tu sesión de sanación está por comenzar",
                            body=f"Recuerda: relájate, hidrátate y mantente receptivo. Tu sesión de Sky Water comienza en menos de 1 hora.",
                            data={"type": "reminder"},
                        )
                    await db.appointments.update_one(
                        {"_id": apt["_id"]},
                        {"$set": {"reminder_sent": True}}
                    )
            except Exception:
                continue
    except Exception as e:
        logging.warning(f"Reminder check failed: {e}")


# ============== ADMIN ROUTES ==============

def verify_admin(request: Request):
    pin = request.headers.get("X-Admin-Pin", "")
    if pin != ADMIN_PIN:
        raise HTTPException(status_code=401, detail="Unauthorized")

@api_router.post("/admin/auth")
async def admin_auth(body: dict):
    pin = body.get("pin", "")
    if pin == ADMIN_PIN:
        return {"valid": True}
    raise HTTPException(status_code=401, detail="PIN incorrecto")

@api_router.get("/admin/orders")
async def admin_get_orders(request: Request, page: int = 1, limit: int = 20):
    verify_admin(request)
    skip = (page - 1) * limit
    total = await db.orders.count_documents({})
    orders = await db.orders.find({}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    for o in orders:
        o.pop("_id", None)
        if "created_at" in o and hasattr(o["created_at"], "isoformat"):
            o["created_at"] = o["created_at"].isoformat()
        if "paid_at" in o and o["paid_at"] and hasattr(o["paid_at"], "isoformat"):
            o["paid_at"] = o["paid_at"].isoformat()
    return {"orders": orders, "total": total, "page": page, "limit": limit}

@api_router.get("/admin/appointments")
async def admin_get_appointments(request: Request, days: int = 7):
    verify_admin(request)
    tz = pytz.timezone("America/Mexico_City")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    end_date = (datetime.now(tz) + timedelta(days=days)).strftime("%Y-%m-%d")
    apts = await db.appointments.find({
        "date": {"$gte": today, "$lte": end_date},
        "status": {"$ne": "cancelled"},
    }).sort([("date", 1), ("time", 1)]).to_list(200)
    for a in apts:
        a.pop("_id", None)
    return {"appointments": apts, "count": len(apts)}

@api_router.get("/admin/referral-stats")
async def admin_referral_stats(request: Request):
    verify_admin(request)
    total_codes = await db.referrals.count_documents({})
    all_refs = await db.referrals.find({}).to_list(1000)
    total_referrals = sum(len(r.get("referred_emails", [])) for r in all_refs)
    top = sorted(all_refs, key=lambda r: len(r.get("referred_emails", [])), reverse=True)[:10]
    top_referrers = [{"email": r["owner_email"], "code": r["code"], "count": len(r.get("referred_emails", []))} for r in top]
    return {"total_codes": total_codes, "total_referrals": total_referrals, "top_referrers": top_referrers}

@api_router.get("/admin/testimonials/pending")
async def admin_pending_testimonials(request: Request):
    verify_admin(request)
    pending = await db.testimonials.find({"status": "pending"}).to_list(100)
    for t in pending:
        t.pop("_id", None)
    return {"testimonials": pending, "count": len(pending)}

@api_router.post("/admin/testimonials/{testimonial_id}/approve")
async def admin_approve_testimonial(testimonial_id: str, request: Request):
    verify_admin(request)
    result = await db.testimonials.update_one(
        {"id": testimonial_id},
        {"$set": {"status": "approved", "verified": True, "moderated_at": datetime.utcnow().isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Testimonio no encontrado")
    return {"success": True}

@api_router.post("/admin/testimonials/{testimonial_id}/reject")
async def admin_reject_testimonial(testimonial_id: str, request: Request):
    verify_admin(request)
    result = await db.testimonials.update_one(
        {"id": testimonial_id},
        {"$set": {"status": "rejected", "moderated_at": datetime.utcnow().isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Testimonio no encontrado")
    return {"success": True}


# ── Meta Conversions API helper ──────────────────────────────────────────────
def _sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()

async def fire_capi_event(
    event_name: str,
    request: Request,
    fbclid: str | None = None,
    fbp: str | None = None,
    event_id: str | None = None,
    custom_data: dict | None = None,
):
    """Send a server-side event to Meta Conversions API."""
    token = META_CAPI_TOKEN or META_GRAPH_TOKEN
    if not token:
        return
    event_id = event_id or str(uuid.uuid4())
    client_ip = request.headers.get('x-forwarded-for', request.client.host if request.client else '').split(',')[0].strip()
    user_agent = request.headers.get('user-agent', '')
    source_url = str(request.url)

    # Build fbc from fbclid if present
    fbc = fbp  # reuse slot for fbc
    if fbclid:
        ts_ms = int(time.time() * 1000)
        fbc = f"fb.1.{ts_ms}.{fbclid}"

    user_data: dict = {}
    if client_ip:
        user_data['client_ip_address'] = _sha256(client_ip)
    if user_agent:
        user_data['client_user_agent'] = user_agent
    if fbc:
        user_data['fbc'] = fbc
    if fbp:
        user_data['fbp'] = fbp

    payload = {
        'data': json.dumps([{
            'event_name': event_name,
            'event_time': int(time.time()),
            'event_id': event_id,
            'event_source_url': source_url,
            'action_source': 'website',
            'user_data': user_data,
            **(({'custom_data': custom_data}) if custom_data else {}),
        }]),
        'access_token': token,
    }
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(
                f'https://graph.facebook.com/v20.0/{META_PIXEL_ID}/events',
                data=payload,
            )
    except Exception as e:
        logging.getLogger(__name__).warning(f'CAPI error: {e}')


# ── Landing page para anuncios Meta Ads ─────────────────────────────────────
STORE_URLS = {
    'ios': 'https://apps.apple.com/us/app/sky-water/id6760956520',
    'android': 'https://play.google.com/store/apps/details?id=com.skywater.app',
    'web': 'https://skywater.site',
}

@app.get("/download/redirect")
async def download_redirect(request: Request, store: str = 'ios', fbclid: str | None = None, fbp: str | None = None):
    """Track store click via CAPI (background) then redirect instantly."""
    event_id = str(uuid.uuid4())
    asyncio.create_task(fire_capi_event(
        event_name='ViewContent',
        request=request,
        fbclid=fbclid,
        fbp=fbp,
        event_id=event_id,
        custom_data={'content_name': f'AppStoreClick_{store}', 'content_category': 'app_download'},
    ))
    url = STORE_URLS.get(store, STORE_URLS['ios'])
    return RedirectResponse(url=url, status_code=302)


@app.get("/download", response_class=HTMLResponse)
async def download_page(request: Request, fbclid: str | None = None, fbp: str | None = None):
    # Fire CAPI Lead event in background — do NOT block HTML render
    event_id = str(uuid.uuid4())
    asyncio.create_task(fire_capi_event(
        event_name='Lead',
        request=request,
        fbclid=fbclid,
        fbp=fbp,
        event_id=event_id,
        custom_data={'content_name': 'Download Page', 'content_category': 'app_download'},
    ))

    # Pass fbclid to redirect links for CAPI deduplication on store clicks
    qs = f"&fbclid={fbclid}" if fbclid else ""
    pixel_id = META_PIXEL_ID

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>Sky Water — Descargar App</title>
<link rel="preconnect" href="https://connect.facebook.net" crossorigin>
<link rel="dns-prefetch" href="https://connect.facebook.net">
<!-- Meta Pixel client-side (dedup with CAPI via event_id) -->
<script async src="https://connect.facebook.net/en_US/fbevents.js"></script>
<script>
window._fbq_event_id = '{event_id}';
window._fbq_pixel   = '{pixel_id}';
window.fbq = window.fbq || function(){{(window.fbq.q=window.fbq.q||[]).push(arguments)}};
window.fbq.loaded = true; window.fbq.version = '2.0'; window.fbq.queue = [];
document.addEventListener('DOMContentLoaded', function() {{
  if (typeof fbq === 'function' && fbq.callMethod) {{
    fbq('init', window._fbq_pixel);
    fbq('track', 'Lead', {{}}, {{eventID: window._fbq_event_id}});
  }} else {{
    // fallback: pixel aún cargando, esperar
    var t = setInterval(function() {{
      if (typeof fbq === 'function' && fbq.callMethod) {{
        clearInterval(t);
        fbq('init', window._fbq_pixel);
        fbq('track', 'Lead', {{}}, {{eventID: window._fbq_event_id}});
      }}
    }}, 100);
  }}
}});
</script>
<noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id={pixel_id}&ev=Lead&noscript=1"/></noscript>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #08111f;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px 16px;
    position: relative;
    overflow: hidden;
  }}
  body::before {{
    content: '';
    position: fixed;
    top: -20%;
    left: 50%;
    transform: translateX(-50%);
    width: 600px;
    height: 600px;
    background: radial-gradient(ellipse, rgba(56,139,255,0.22) 0%, transparent 70%);
    pointer-events: none;
  }}
  body::after {{
    content: '';
    position: fixed;
    bottom: -10%;
    left: 20%;
    width: 400px;
    height: 400px;
    background: radial-gradient(ellipse, rgba(100,60,220,0.15) 0%, transparent 70%);
    pointer-events: none;
  }}
  .card {{
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 28px;
    padding: 36px 28px 32px;
    max-width: 390px;
    width: 100%;
    text-align: center;
    backdrop-filter: blur(20px);
    position: relative;
    z-index: 1;
  }}
  .badge {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: rgba(56,139,255,0.15);
    border: 1px solid rgba(56,139,255,0.3);
    border-radius: 20px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 600;
    color: #6db3ff;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 20px;
  }}
  .badge-dot {{
    width: 7px;
    height: 7px;
    background: #3d9bff;
    border-radius: 50%;
    animation: pulse 2s infinite;
  }}
  @keyframes pulse {{
    0%,100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.5; transform: scale(1.4); }}
  }}
  .logo {{
    font-size: 12px;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: rgba(255,255,255,0.35);
    margin-bottom: 10px;
  }}
  h1 {{
    font-size: 32px;
    font-weight: 800;
    color: #ffffff;
    margin-bottom: 10px;
    letter-spacing: -0.8px;
    line-height: 1.15;
  }}
  .tagline {{
    font-size: 15px;
    color: rgba(255,255,255,0.55);
    margin-bottom: 24px;
    line-height: 1.55;
  }}
  .social-proof {{
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 0;
    margin-bottom: 24px;
    flex-wrap: wrap;
  }}
  .proof-item {{
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 0 14px;
  }}
  .proof-item + .proof-item {{
    border-left: 1px solid rgba(255,255,255,0.12);
  }}
  .proof-value {{
    font-size: 15px;
    font-weight: 700;
    color: #ffffff;
  }}
  .proof-label {{
    font-size: 11px;
    color: rgba(255,255,255,0.4);
    margin-top: 2px;
  }}
  .stars {{ color: #f5c842; font-size: 13px; letter-spacing: 1px; }}
  .testimonial {{
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 16px 18px;
    margin-bottom: 28px;
    text-align: left;
  }}
  .testimonial-text {{
    font-size: 13.5px;
    color: rgba(255,255,255,0.72);
    line-height: 1.55;
    font-style: italic;
    margin-bottom: 10px;
  }}
  .testimonial-author {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .avatar {{
    width: 28px;
    height: 28px;
    background: linear-gradient(135deg,#3d9bff,#7c4dff);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    color: white;
    flex-shrink: 0;
  }}
  .author-name {{
    font-size: 12px;
    font-weight: 600;
    color: rgba(255,255,255,0.6);
  }}
  .author-detail {{
    font-size: 11px;
    color: rgba(255,255,255,0.35);
  }}
  .btn {{
    display: flex;
    align-items: center;
    width: 100%;
    padding: 16px 20px;
    border-radius: 16px;
    text-decoration: none;
    margin-bottom: 10px;
    transition: transform 0.15s ease, opacity 0.15s ease, box-shadow 0.15s ease;
    color: #ffffff;
    position: relative;
    overflow: hidden;
  }}
  .btn:active {{ transform: scale(0.97); opacity: 0.88; }}
  .btn-icon {{
    flex-shrink: 0;
    margin-right: 14px;
  }}
  .btn-text {{ flex: 1; text-align: left; }}
  .btn-main {{
    font-size: 15px;
    font-weight: 700;
    display: block;
    line-height: 1.2;
  }}
  .btn-sub {{
    font-size: 11px;
    opacity: 0.6;
    display: block;
    margin-top: 2px;
  }}
  .btn-arrow {{
    font-size: 18px;
    opacity: 0.5;
    margin-left: 8px;
  }}
  .btn-ios {{
    background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
    border: 1px solid rgba(255,255,255,0.15);
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  }}
  .btn-ios:hover {{ box-shadow: 0 6px 28px rgba(0,0,0,0.6); }}
  .btn-android {{
    background: linear-gradient(135deg, #1557c0 0%, #1a73e8 100%);
    border: 1px solid rgba(26,115,232,0.4);
    box-shadow: 0 4px 20px rgba(26,115,232,0.25);
  }}
  .btn-android:hover {{ box-shadow: 0 6px 28px rgba(26,115,232,0.4); }}
  .btn-web {{
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.13);
  }}
  .divider {{
    color: rgba(255,255,255,0.18);
    font-size: 11px;
    margin: 4px 0 14px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
  }}
  .trust {{
    margin-top: 20px;
    font-size: 11px;
    color: rgba(255,255,255,0.28);
    letter-spacing: 0.3px;
  }}
  .trust span {{ margin: 0 4px; }}
</style>
</head>
<body>
<div class="card">
  <div class="badge"><span class="badge-dot"></span>Disponible ahora</div>
  <div class="logo">Sky Water</div>
  <h1>Sana desde<br>donde estás</h1>
  <p class="tagline">Sanación energética a distancia.<br>Miles de personas ya lo comprueban.</p>

  <div class="social-proof">
    <div class="proof-item">
      <div class="proof-value stars">★★★★★</div>
      <div class="proof-label">4.9 rating</div>
    </div>
    <div class="proof-item">
      <div class="proof-value">12,000+</div>
      <div class="proof-label">descargas</div>
    </div>
    <div class="proof-item">
      <div class="proof-value">7</div>
      <div class="proof-label">niveles</div>
    </div>
  </div>

  <div class="testimonial">
    <div class="testimonial-text">"Llevaba 3 años con dolor de ciático. Después de la primera sesión de Sky Water dormí sin dolor por primera vez."</div>
    <div class="testimonial-author">
      <div class="avatar">R</div>
      <div>
        <div class="author-name">Rodrigo M.</div>
        <div class="author-detail">Nervio ciático · Guadalajara</div>
      </div>
    </div>
  </div>

  <a class="btn btn-ios" href="/download/redirect?store=ios{qs}"
     onclick="fbq('track','ViewContent',{{content_name:'AppStoreClick_ios'}})">
    <span class="btn-icon">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
        <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"/>
      </svg>
    </span>
    <span class="btn-text">
      <span class="btn-main">Descargar en iPhone</span>
      <span class="btn-sub">App Store · Gratis</span>
    </span>
    <span class="btn-arrow">›</span>
  </a>

  <a class="btn btn-android" href="/download/redirect?store=android{qs}"
     onclick="fbq('track','ViewContent',{{content_name:'AppStoreClick_android'}})">
    <span class="btn-icon">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="white">
        <path d="M3.18 23.76c.37.21.8.24 1.2.09l11.6-6.7-2.53-2.53L3.18 23.76zm16.3-10.34L17 11.97l-2.7 2.7 2.68 2.68 2.51-1.45c.71-.41.71-1.48-.01-1.88zM1.34.62C1.13.85 1 1.2 1 1.63v20.74c0 .43.13.78.35 1.01l.06.05 11.62-11.62v-.27L1.34.62zm14.48 8.35L4.22.21C3.82.06 3.39.1 3.03.3L13.6 10.88l2.22-1.91z"/>
      </svg>
    </span>
    <span class="btn-text">
      <span class="btn-main">Descargar en Android</span>
      <span class="btn-sub">Google Play · Gratis</span>
    </span>
    <span class="btn-arrow">›</span>
  </a>

  <div class="divider">— o también —</div>

  <a class="btn btn-web" href="/download/redirect?store=web{qs}"
     onclick="fbq('track','ViewContent',{{content_name:'WebClick'}})">
    <span class="btn-icon">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="rgba(255,255,255,0.7)">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
      </svg>
    </span>
    <span class="btn-text">
      <span class="btn-main">Usar en el navegador</span>
      <span class="btn-sub">skywater.site</span>
    </span>
    <span class="btn-arrow">›</span>
  </a>

  <div class="trust">
    <span>Pago seguro</span>·<span>Soporte 24/7</span>·<span>Sin riesgo</span>
  </div>
</div>
</body>
</html>""", status_code=200)

# ── ROAS Dashboard ─────────────────────────────────────────────────────────
@app.get("/api/admin/roas")
async def roas_dashboard(request: Request, days: int = 7, pin: str = ""):
    """Admin endpoint: Meta Ads spend vs backend revenue → ROAS."""
    if pin != ADMIN_PIN:
        raise HTTPException(status_code=403, detail="Invalid PIN")

    token = META_GRAPH_TOKEN
    date_preset_map = {7: 'last_7d', 14: 'last_14d', 30: 'last_30d'}
    date_preset = date_preset_map.get(days, 'last_7d')

    ads_data = []
    total_spend = 0.0
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f'https://graph.facebook.com/v20.0/{META_AD_ACCOUNT}/insights',
                params={
                    'fields': 'ad_id,ad_name,spend,impressions,clicks,ctr,cpc,actions',
                    'level': 'ad',
                    'date_preset': date_preset,
                    'filtering': json.dumps([{'field': 'adset.campaign_id', 'operator': 'EQUAL', 'value': '120245337508400070'}]),
                    'access_token': token,
                }
            )
        for ad in r.json().get('data', []):
            spend = float(ad.get('spend', 0))
            total_spend += spend
            actions = {a['action_type']: int(a['value']) for a in ad.get('actions', [])}
            ads_data.append({
                'name': ad.get('ad_name', ''),
                'spend_mxn': round(spend, 2),
                'impressions': int(ad.get('impressions', 0)),
                'clicks': int(ad.get('clicks', 0)),
                'ctr_pct': round(float(ad.get('ctr', 0)), 2),
                'cpc_mxn': round(float(ad.get('cpc', 0)), 3),
                'landing_page_views': actions.get('landing_page_view', 0),
                'video_views': actions.get('video_view', 0),
            })
    except Exception as e:
        logging.getLogger(__name__).error(f'ROAS Meta API error: {e}')

    # Revenue from MongoDB
    now = datetime.utcnow()
    since = now - timedelta(days=days)
    total_revenue = 0.0
    order_count = 0
    cost_per_lead = 0.0
    try:
        pipeline = [
            {'$match': {'created_at': {'$gte': since}, 'payment_status': 'approved'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}, 'count': {'$sum': 1}}}
        ]
        async for doc in db.orders.aggregate(pipeline):
            total_revenue = float(doc.get('total', 0))
            order_count = int(doc.get('count', 0))
    except Exception as e:
        logging.getLogger(__name__).error(f'ROAS MongoDB error: {e}')

    # Lead count from CAPI events approximation (LP views as proxy)
    total_lp = sum(a['landing_page_views'] for a in ads_data)
    if total_lp > 0:
        cost_per_lead = round(total_spend / total_lp, 2)

    roas = round(total_revenue / total_spend, 2) if total_spend > 0 else 0

    return {
        'period_days': days,
        'total_spend_mxn': round(total_spend, 2),
        'total_revenue_mxn': round(total_revenue, 2),
        'total_orders': order_count,
        'roas': roas,
        'total_landing_page_views': total_lp,
        'cost_per_lead_mxn': cost_per_lead,
        'ads': sorted(ads_data, key=lambda x: x['spend_mxn'], reverse=True),
    }


# Include the router (MUST be after all route definitions)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[
        "http://localhost:3000",
        "https://skywater.site",
        "https://www.skywater.site",
        "http://localhost:8001",
        "https://skywater-five.vercel.app",
        "https://*.expo.dev",
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-Admin-Pin", "x-api-key", "Accept"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def reminder_check_loop():
    """Background loop: check every 15 min for appointments needing reminders."""
    import asyncio
    while True:
        await asyncio.sleep(900)  # 15 minutes
        await send_pending_reminders()


@app.on_event("startup")
async def startup_db_client():
    """Create database indexes on startup to enforce slot uniqueness."""
    import asyncio
    try:
        # Unique compound index prevents two active bookings at the same date+time
        await db.appointments.create_index(
            [("date", 1), ("time", 1)],
            unique=True,
            partialFilterExpression={"status": {"$ne": "cancelled"}},
            name="unique_active_slot",
        )
        logger.info("MongoDB indexes created/verified successfully")
    except Exception as e:
        logger.warning(f"Index creation warning (may already exist): {e}")

    # Start push notification reminder loop
    asyncio.create_task(reminder_check_loop())


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
# trigger redeploy

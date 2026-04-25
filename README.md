# 🚀 PyInstaller GUI — CustomTkinter Edition

Una interfaz gráfica moderna, elegante y potente para convertir tus scripts de Python (`.py`) en ejecutables independientes (`.exe`) de forma sencilla, utilizando **PyInstaller** y **CustomTkinter**.

![Versión](https://img.shields.io/badge/version-1.1-blue.svg)
![Python](https://img.shields.io/badge/python-3.7+-green.svg)
![Licencia](https://img.shields.io/badge/license-MIT-blue.svg)

---

## ✨ Características Principales

- **🎨 Interfaz Moderna**: Diseño "Dark Mode" basado en tarjetas, limpio y profesional diseñado con `customtkinter`.
- **📦 Empaquetado Completo**: Soporta modo `--onefile` (un solo archivo) y `--onedir` (carpeta con dependencias).
- **🖼️ Gestor de Íconos Inteligente**: 
    - Selección de imágenes en formatos comunes (PNG, JPG, WebP, BMP).
    - **Conversión automática** a `.ico` multi-resolución (16px a 256px) para una apariencia nativa perfecta en Windows.
- **⚙️ Opciones Avanzadas**:
    - **Windowed/No Console**: Oculta la consola para aplicaciones GUI.
    - **Hidden Imports**: Gestión fácil de módulos no detectados automáticamente.
    - **Add Data**: Incorpora archivos externos o carpetas en el ejecutable.
    - **UPX & Strip**: Opciones de compresión y optimización de tamaño.
- **📝 Consola en Tiempo Real**: Visualiza el proceso de compilación con logs coloreados por severidad (Errores, Advertencias, Info).
- **💾 Persistencia**: Guarda y carga automáticamente tus últimas configuraciones en un archivo JSON.
- **🛠️ Auto-instalación**: El script detecta si faltan librerías críticas y ofrece instalarlas automáticamente.

---

## 🛠️ Requisitos e Instalación

### Requisitos previos
Asegúrate de tener instalado Python 3.7 o superior.

### Instalación de dependencias
El script intentará instalar lo necesario al ejecutarse, pero puedes instalarlo manualmente para mayor control:

```bash
pip install customtkinter pyinstaller pillow
```

---

## 🚀 Cómo usar

1. **Seleccionar Script**: Clica en "Examinar" en la sección de Script Python y elige tu archivo `.py`.
2. **Personalizar**: 
   - Cambia el nombre del archivo de salida.
   - Selecciona un ícono (el programa lo convertirá por ti si no es `.ico`).
3. **Configurar**: Marca las opciones deseadas (recomendamos `--onefile` y `--windowed` para apps de escritorio).
4. **Compilar**: Pulsa el botón **▶ Compilar**.
5. **Listo**: Una vez termine, se abrirá un mensaje confirmando el éxito y dándote la opción de abrir la carpeta `dist/` donde reside tu ejecutable.

---

## 📸 Captura de Pantalla

*(Aquí puedes insertar una captura de pantalla de la interfaz una vez la tengas)*

---

## 📂 Estructura del Proyecto

```text
.
├── py_installer.py            # Script principal (GUI)
├── pyinstaller_gui_config.json # Configuración guardada (se genera al usar)
├── icon.ico                   # Ícono generado automáticamente
└── README.md                  # Este archivo
```

---

## 📝 Notas de Versión (v1.1)

- Se ha añadido un motor de construcción de íconos manual con `struct` para evitar bugs de Pillow y garantizar alta calidad en Windows.
- Soporte para cancelación de procesos en curso.
- Mejora en la persistencia de datos (JSON).

---

## 🤝 Contribuciones

¡Las sugerencias y mejoras son bienvenidas! Siente la libertad de clonar el repositorio y enviar un Pull Request.

---

## ⚖️ Licencia

Este proyecto está bajo la Licencia MIT. Siéntete libre de usarlo para tus proyectos personales o comerciales.

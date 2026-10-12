# Publicación privada y recuperación

## Actualización de un repositorio existente

El remoto configurado para este proyecto es `Valentinhp/VALENZA`. La rama de
trabajo de esta actualización es `desarrollo/suscripciones-msi`; no se debe
asumir que los cambios ya están en `main`.

Antes de publicar, ejecuta la suite sintética indicada en el README y revisa:

```powershell
git remote -v
git branch --show-current
git status --short
git ls-files --others --exclude-standard
git diff --check
```

Las eliminaciones de `src/sgccc` y los nuevos archivos de `src/valenza` son parte
de la misma migración: deben incluirse juntos. Conserva los assets del paquete
y los SVG de `logos/`. No añadas `output/`, `tmp/`, bases ni respaldos con `-f`.

Para preparar el commit local tras revisar los archivos:

```powershell
git add -- .gitattributes .gitignore README.md CHANGELOG.md pyproject.toml Abrir-Valenza.cmd docs src tests tools logos
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only
git commit -m "Actualiza Valenza, interfaz Warm Finance y reportes financieros"
```

Comprueba la privacidad y la rama destino antes del push. Para publicar esta
rama y revisarla antes de integrarla en `main`:

```powershell
gh repo view Valentinhp/VALENZA --json nameWithOwner,isPrivate,visibility,url
git push -u origin desarrollo/suscripciones-msi
```

Estos comandos son instrucciones para una publicación posterior; la preparación
de documentación no realiza el push ni crea etiquetas de versión.

## Primera publicación y recuperación histórica

La etiqueta anotada `v0.1.0-pre-estabilizacion` conserva el código anterior a
estabilización, suscripciones y ampliaciones de MSI. No sustituye un respaldo
cifrado de datos: las bases y sus respaldos quedan fuera de Git.

Antes de publicar:

1. Confirmar cuenta y nombre del repositorio con su propietario.
2. Crear un repositorio **Private**, vacío, sin inicializar README ni licencia.
3. Verificar mediante la API autenticada que `private` sea `true` y que
   `visibility` sea `private`, además de confirmar propietario y nombre.
4. Configurar `origin` solo con la URL verificada, sin tokens ni contraseñas.
5. Revisar archivos e historial y pedir confirmación final indicando commit,
   etiqueta y repositorio exactos antes de subir contenido.
6. Con esa confirmación, subir `main` y la etiqueta; comprobar ambas referencias
   remotas y verificar nuevamente la privacidad.

Con GitHub CLI instalado y autenticado, la consulta de privacidad es:

```powershell
gh repo view CUENTA/REPOSITORIO --json nameWithOwner,isPrivate,visibility,url
```

No subir contenido si no puede verificarse la privacidad. Usa autenticación de
GitHub o del administrador de credenciales, nunca tokens incluidos en la URL
ni contraseñas de Valenza. Los PDFs e imágenes versionados son únicamente los
fixtures sintéticos revisados, con números e identidades ficticios.

Para recuperar el código sin descartar cambios en curso:

```powershell
git switch -c recuperar-base v0.1.0-pre-estabilizacion
```

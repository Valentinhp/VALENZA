# Publicación privada y recuperación

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

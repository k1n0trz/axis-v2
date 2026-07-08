# Auditoria profunda Ads Axis - 2026-07-07

Periodo de datos de plataforma: 2026-06-01 a 2026-07-06 para dias completos. Corte parcial Meta: 2026-07-07.  
Archivo bruto: `data/deep_ads_audit_2026-07-07.json`.

## Resumen ejecutivo

La preocupacion no es una sola cosa. Hay tres frentes distintos:

1. **Meta Uva Colombia no esta roto; esta mezclando aprendizajes.** Hidratante esta vendiendo, pero el adset mezcla compradores, base email y lookalike 1-3% en un solo RMK, asi que no sabes si estas comprando demanda caliente, expansion parecida o recompra. La UGC nueva tenia senales buenas antes de pausarse; reactivar la campana vieja hoy la dejo arrancando con CTR bajo y sin compra todavia.
2. **Bali Lovense tiene demanda, pero el valor de conversion esta roto o incompleto.** La campana Lovense marca CPA aceptable, pero ROAS 0.73 porque varias conversiones llegan con valor 0. Con ese tracking, cualquier estrategia basada en valor o lectura de ROAS va a mentir.
3. **Uva Ecuador esta optimizando a conversiones baratas que no parecen compra.** PMax reporta 884 conversiones con CPA de 1.230 COP, pero ROAS 0.45. Eso huele a set de conversiones contaminado por microeventos, WhatsApp o valores mal importados.

Limitaciones reales:

- Laboratorio Helti `386-688-1158`: Google Ads devolvio `403 Forbidden`.
- Copa Uva MX `614-516-5793`: Google Ads devolvio `401 Unauthorized`. Ademas, en tests del repo aparece otro id historico `614-371-5017`; conviene confirmar si el ID que me diste es el final.
- La base local de Axis esta desactualizada para pauta: llega hasta 2026-06-04. Por eso use APIs directas.

## Meta Ads - Uva Colombia

### 02/07/26 | Ventas | Hidratante

Datos al 2026-07-06:

- Presupuesto campana: 50.000 COP/dia.
- Gasto: 240.388 COP.
- Compras Meta: 6.
- CPA compra: 40.065 COP.
- ROAS compra: 3.54.
- CTR: 1.18%.
- CPC: 1.023 COP.
- Frecuencia: 2.35.
- Hoy 2026-07-07 parcial: 13.276 COP, 940 impresiones, 7 clics, 0 compras, CTR 0.74%, CPM 14.123 COP.

Lectura:

La campana no esta muerta. Para un SKU nuevo de 59.900 COP, un ROAS 3.54 con 6 compras en pocos dias es senal valida, pero no escalable todavia. El problema es estructural: el unico adset `02/07/26 | RMK` mezcla compradores, emails y lookalike 1-3%, mujeres 18-45 en ciudades, con Advantage Audience encendido. Ese adset no te permite saber si el producto esta funcionando por interes real del mercado o por recompra/cross-sell de una audiencia caliente.

Acciones especificas:

- Separar el adset en tres brazos durante 72 horas con presupuesto ABO:
  - `HID | RMK caliente | 7-180d`: visitantes, ATC, IC, engagers IG/FB, video viewers; excluir compradores de Hidratante si existe evento por SKU.
  - `HID | Compradoras Uva | 365d`: compradores copa/disco/jabon, sin lookalike dentro; mensaje de complemento de rutina.
  - `HID | LAL compradores | 1-3%`: lookalike limpio, excluir compradores y RMK caliente; mensaje de problema/beneficio.
- Mantener presupuesto total similar al actual, no escalar todavia: 15k / 20k / 15k COP diarios. Si el brazo de compradoras sostiene CPA menor a 30k, moverlo a 25k y bajar LAL.
- Pausar o aislar creativos con gasto sin compra:
  - Pausar: `Spa en casa`, `Lanzamiento`, `Skincare 2`, `Resequedad`, `Irritacion` si pasan 1.2x CPA objetivo sin compra.
  - Mantener y duplicar variantes: `Postbioticos`, `Piel intima`, `Cambios hormonales`, `Test Video 1`.
  - Reducir el peso de `Post | Incomodidad`: gasto alto, ROAS medio; en Instagram Feed gasto 46.237 COP con 0 compras.
- No venderlo como "producto nuevo" en frio. Venderlo como **solucion de momento de uso**:
  - post-depilacion
  - ejercicio/ropa ajustada
  - menstruacion
  - postparto/lactancia
  - premenopausia/menopausia
- Subir AOV: el producto vale 59.900 COP y el sitio comunica envio gratis desde 70.000/90.000 COP segun bloque visible. La oferta obvia no es descuento, es bundle:
  - `Hidratante + jabon intimo`: supera umbral y aumenta plausibilidad de rutina.
  - `Kit bienestar`: usarlo como upsell en PDP y remarketing 1 dia despues de visita.
- Ajuste de landing: la pagina tiene argumentos fuertes, pero el primer bloque debe mostrar antes:
  - "uso externo, diario, no interno"
  - dermatologicamente probado / hipoalergenico / no irritante
  - postbioticos + acido hialuronico
  - bundle para envio gratis

### 26/06/26 | Ventas | Ugc

Datos al 2026-07-06:

- Estado: pausada.
- Presupuesto campana: 40.000 COP/dia.
- Gasto: 418.941 COP.
- Compras: 13.
- CPA compra: 32.226 COP.
- ROAS: 3.05.
- CTR: 1.62%.
- CPC: 498 COP.

Creativos:

- `UGC | Experiencia UVA`: 229.978 COP, 9 compras, ROAS 3.71. Ganador claro.
- `Reel | Tip de amigas`: 50.931 COP, 2 compras, ROAS 5.88. Poco gasto, muy prometedor.
- `UGC | Entregarme a la ciencia`: 95.825 COP, 2 compras, ROAS 1.33. Solo conservar si aporta aprendizaje cualitativo.
- `Voy a decir algo`: 34.232 COP, 0 compras. Pausar.
- `Eli 2`: 7.975 COP, 0 compras. No decidir todavia, pero no escalar.

Lectura:

Pausar esta campana fue probablemente defensivo, no basado en mala performance. CPA de 32k y ROAS 3.05 en UGC para copa es aprovechable. Lo que si estaba mal era dejar demasiados UGC sin corte estadistico.

Acciones:

- Reabrir el concepto UGC, pero no necesariamente la campana exacta.
- Crear `UGC | Winners | Copa | 2026-07` con solo:
  - `Experiencia UVA`
  - `Tip de amigas`
  - una nueva version de `Entregarme a la ciencia` con hook cambiado, no la misma pieza.
- Regla operativa:
  - Si un creativo llega a 1.2x CPA objetivo sin ATC/IC fuerte: pausar.
  - Si llega a 2 compras con ROAS > 3: duplicar variacion de hook, no tocar pieza ganadora original.
- No meter Hidratante y Copa en el mismo aprendizaje. La UGC de copa vende dolor de cambio menstrual; Hidratante vende rutina/cuidado externo.

### 10/11/25 | Ventas | UGC reactivada

Estado actual:

- Activa, presupuesto 60.000 COP/dia.
- No tuvo gasto del 2026-06-01 al 2026-07-06.
- Hoy 2026-07-07 parcial: 5.958 COP, 478 impresiones, 3 clics, 2 link clicks, 0 compras, CTR 0.63%, CPC 1.986 COP.

Lectura:

No hay datos suficientes para condenarla, pero el arranque parcial es flojo. El adset viejo `29/10/25 | Open Adv` apunta a Colombia completo, mujeres 18-50, con Advantage Audience apagado. Es peor laboratorio que la estructura nueva por ciudades.

Acciones:

- No dejarla consumir 60k/dia en automatico hasta que tenga 24-48h limpias.
- Bajar temporalmente a 25k-30k o pasar ganadores a una estructura nueva.
- Si se mantiene la campana vieja, usarla solo como contenedor de historico y limpiar anuncios:
  - Mantener activos: versiones 07/07 de `Entregarme a la ciencia`, `Eli 2`, `Voy a decir algo` solo si en 24h superan 1% CTR y generan LPV barato.
  - Pausar si en 15k-20k COP no supera 0.9% CTR o no genera add-to-cart.
- Crear un segundo adset de ciudades, mujeres 18-45, Advantage Audience controlado, para comparar contra Colombia abierto. No mezclar.

## Google Ads - Bali Store

### 19/06/26 | Ventas | Search | Lovense

Datos 2026-06-01 a 2026-07-06:

- Presupuesto: 40.000 COP/dia.
- Gasto: 562.005 COP.
- Clics: 693.
- Conversiones: 16.96.
- CPA: 33.138 COP.
- Valor conversion: 412.482 COP.
- ROAS: 0.73.
- Estrategia: Maximize Conversions.

Lectura:

La campana no fracasa por demanda. Fracasa por calidad de medicion/segmentacion. Hay conversiones con valor 0 en varios grupos; eso vuelve inutil el ROAS y te impide saber si Lovense realmente esta perdiendo plata o si el valor no esta llegando desde Shopify/GA4.

Ad groups:

- `Lush Mini`: 66.465 COP, 3 conversiones, 185.765 COP valor. Mejor candidato.
- `Domi 2`: 92.282 COP, 3.96 conversiones, 134.952 COP valor. Candidato con ajuste.
- `Lovense Lush 2`: 68.039 COP, 2 conversiones, 91.765 COP valor.
- `Lush 4`: 122.522 COP, 4 conversiones, valor 0. No escalar hasta arreglar value.
- `Mini Sex Machine`: 81.221 COP, 3 conversiones, valor 0.
- `Lovense Nora`: 74.088 COP, 1 conversion, valor 0.
- `Lush Anal`: 38.617 COP, 0 conversiones.
- `Hush 2`: 18.572 COP, 0 conversiones.

Acciones:

- Primero tracking:
  - Revisar si `purchase` importa valor desde Shopify/GA4 para productos Lovense.
  - Auditar por order id si esas conversiones de valor 0 son compras reales, WhatsApp, add-to-cart o eventos modelados.
  - Hasta corregirlo, no migrar a tROAS ni juzgar por ROAS.
- Negativas inmediatas dentro de Lovense:
  - `vibrador` broad cuando no incluya Lovense/modelo.
  - `plug anal` fuera de Hush/Lush Anal si no convierte.
  - `sex shop`, `juguetes sexuales`, `juguetes sexuales para mujeres`, `estrechante sen intimo`.
  - variantes informacionales o no modelo: `lush juguete`, `vibrador bala` si el CTR/CPA sigue sin compra.
- Exact/phrase por modelo:
  - Campana o grupos separados por `Lush Mini`, `Lush 4`, `Domi 2`, `Lush 2`, `Nora`, `Sex Machine`.
  - El ad copy debe decir modelo + entrega + garantia + discrecion, no erotizar.
- Cannibalizacion:
  - Hay busquedas Lovense gastando en campañas genericas CO/Medellin/Bogota.
  - Meter `lovense`, `lush`, `domi`, `hush`, `nora`, `ferri`, `max 2`, `sex machine lovense` como negativas exact/phrase en genericas, salvo terminos que historicamente conviertan mejor alli.
- Presupuesto:
  - No subir de 40k/dia hasta tener value correcto.
  - Redistribuir internamente: 40% Lush Mini, 25% Domi 2, 20% Lush 2/Lush 4, 15% exploracion.

### 11/09/25 | Shopping | P-Max | COL

Datos:

- Presupuesto: 95.000 COP/dia.
- Gasto: 3.464.338 COP.
- Conversiones: 59.80.
- CPA: 57.936 COP.
- Valor: 7.936.478 COP.
- ROAS: 2.29.

Lectura:

PMax esta aportando, pero por debajo de Search CO y Search Medellin. El gasto esta disperso en productos con cero conversiones y mezclando categorias muy distintas: lenceria, lubricantes, retardantes, Uva, Lovense, condones, juegos.

Acciones:

- Crear etiquetas de feed por margen y rol:
  - `core_high_margin`: condones, retardantes, lubricantes ganadores, kits.
  - `premium_lovense`: Lovense y accesorios con valor correcto.
  - `low_signal_zero`: productos con gasto > 10k y 0 valor.
  - `cross_brand_uva`: productos Uva dentro de Bali, solo si hay intencion de cross-sell.
- Excluir o aislar por listing group los productos con gasto y 0 valor recurrente:
  - Lenceria Duna, varios Elixir sin venta, Potenciador PMX 500ml, Frequency, juegos sin conversion, accesorios Lovense sin venta.
- Mantener e impulsar productos con ROAS alto aunque tengan bajo gasto:
  - Condones Poseidon, Adaptador Lovense Bluetooth USB, Copa Intimina, algunos aceites y lubricantes con conversion real.
- Separar PMax por margen si hay suficiente volumen. Una PMax unica esta optimizando a conversion promedio, no a rentabilidad.

## Google Ads - Uva Ecuador

Datos:

- Search EC: 1.091.896 COP, 51 conversiones, CPA 21.410, ROAS 0.43.
- PMax EC: 1.087.973 COP, 884.15 conversiones, CPA 1.231, ROAS 0.45.
- Ambas con Maximize Conversions.

Lectura:

La PMax esta generando muchisimas conversiones baratas pero poco valor. Eso no es performance real; es un problema de definicion de conversion o de valor. Si fueran compras, el valor no podria ser tan bajo. La cuenta esta entrenando al algoritmo a buscar eventos baratos.

Acciones:

- Revisar conversion goals:
  - Dejar como primaria solo compra/lead calificado final.
  - Pasar WhatsApp click, view content, add-to-cart e iniciar checkout a secundaria si no representan ingreso.
  - Si WhatsApp es la venta real, importar cierre o valor esperado por conversacion, no dejarlo como conversion plana.
- Separar Search:
  - `Brand Uva`: uva copa, copa menstrual uva, uva copa menstrual.
  - `Categoria alta intencion`: copa menstrual + ciudad/precio/ecuador/quito/guayaquil.
  - `Competidores y retail`: Fybeca, Supermaxi, DivaCup, Eva. Presupuesto capado y copy comparativo suave.
  - `Panties`: no debe convivir con copa/intimina si el margen/conversion son distintos.
- Negativas:
  - `leonisa catalogo`, `modibodi`, `nosotras`, busquedas no vendidas o de catalogo.
  - `aplicadores de copa menstrual` si no hay producto o landing especifica.
- PMax:
  - Bajar presupuesto 30%-50% hasta corregir conversiones primarias.
  - No pasar a tROAS hasta normalizar valores.
  - Usar asset groups por categoria real: Copa, Disco, Panties, Kits.

## Google Ads - Laboratorio Helti y Copa Uva MX

No pude hacer analisis de performance por bloqueo de acceso:

- Helti `386-688-1158`: `403 Forbidden`.
- MX `614-516-5793`: `401 Unauthorized`.

Acciones para desbloquear:

- Verificar que el refresh token pertenece a un usuario con acceso directo o via MCC a esas cuentas.
- Confirmar `GOOGLE_ADS_LOGIN_CUSTOMER_ID`.
- Confirmar que el developer token aprobado esta habilitado para esos customer IDs.
- En MX, confirmar si el id correcto es `614-516-5793` o el historico que aparece en tests: `614-371-5017`.

## Contexto de mercado y politicas

- Google clasifica sex toys y productos de actividad sexual como contenido sexual restringido: pueden correr en Search, pero no en Display/YouTube y dependen de edad, SafeSearch, ley local y query del usuario. Fuente: Google Ads Sexual content policy.
- Meta permite salud sexual/reproductiva con restricciones, pero el foco debe estar en salud/eficacia, no placer o enhancement. Esto importa para Hidratante y para creativos de Uva: cuidado externo, piel, dermatologia y etapas hormonales son mas seguros que lenguaje sexual.
- El mercado sexual wellness sigue creciendo, pero las marcas reportan friccion fuerte en Meta/Google/TikTok. Eso favorece creatividad educativa, lenguaje de bienestar y landing pages con prueba/autoridad, no promesas erotizadas.
- Lovense sigue siendo una marca de alta intencion por innovacion/app-control; Lush 4 y Lush Mini son productos recientes en el ecosistema. Para Search, el angulo ganador debe ser modelo especifico + disponibilidad local + envio discreto + garantia.

Fuentes externas:

- Google Ads policy: https://support.google.com/adspolicy/answer/6023699?hl=en
- Copa Uva Hidratante: https://copauva.com/producto/hidratante-intimo-uva/
- Vogue Business sobre restricciones en sexual wellness: https://www.voguebusiness.com/story/beauty/sex-sells-what-about-sexual-wellness
- Vogue sobre sexual wellness y censura de plataformas: https://www.vogue.com/article/can-luxury-sell-sexual-wellness
- Lovense overview/product cadence: https://en.wikipedia.org/wiki/Lovense

## Prioridades de esta semana

1. Corregir Google Ads conversion value en Bali Lovense y Uva Ecuador.
2. Reabrir UGC Copa con solo ganadores, no con todo el set creativo.
3. Separar Hidratante en RMK caliente, compradoras Uva y LAL.
4. Limpiar busquedas Lovense en campañas genericas de Bali.
5. Reestructurar PMax Bali con etiquetas de feed por margen/rol.
6. Desbloquear acceso Helti/MX antes de gastar tiempo interpretando datos inexistentes.

## Addendum 2026-07-07 - Correccion Copa Uva MX

La cuenta MX si respondio al consultar el customer ID correcto `614-371-5017`. El bloqueo inicial se produjo porque en el brief inicial venia `614-516-5793`, que devolvio `401 Unauthorized`. La captura y los tests del proyecto apuntan a `614-371-5017`.

Archivo bruto adicional: `data/deep_google_mx_2026-07-07.json`.

Datos 2026-06-01 a 2026-07-06:

- Total Google Ads MX: 25.078 MXN de gasto y 65 conversiones.
- PMax `16/04/26 | Ventas | Pmax | Mx`: 12.573,70 MXN, 2.944 clics, 182.574 impresiones, 41,33 conversiones, valor 0.
- Search `30/01/26 | Ventas | Search | MX`: 12.504,48 MXN, 338 clics, 13.930 impresiones, 23,67 conversiones, valor 17.
- PMax CPA: 304,20 MXN. Search CPA: 528,36 MXN.
- Ambas usan Maximize Conversions.

Lectura: MX no esta bloqueada; esta mal medida. PMax reporta 41 conversiones con valor 0 y Search reporta valor 17 para 23,67 conversiones. Eso impide leer ROAS y vuelve peligroso escalar con Smart Bidding, porque el sistema aprende a perseguir eventos sin valor economico confiable.

Acciones especificas MX:

- Corregir conversion goals antes de escalar: dejar primaria solo compra o lead calificado final. Si la conversion real es WhatsApp, importar cierres o asignar valor esperado real por conversacion.
- Separar Search en `Brand`, `Categoria`, `Competencia` y `Disco/Panties`. No dejar `copa menstrual uva`, `copa menstrual`, `disco menstrual`, `calzones` y terminos genericos de higiene en la misma lectura.
- Crear negativas inmediatas: `gratis`, `muestras gratis`, `ginecologia online`, `ginecologo en linea`, `flo`, `farmacia en mexico`, `tampax contact`, `what is the meaning`, `lenceria`, `venta de lenceria`, `toalla de tela`, `saba empresa`, `proyecto copita`.
- Brand MX tiene demanda: `copa menstrual uva` genero 20 clics y 3 conversiones, pero valor 0. Defenderlo con campana brand separada.
- PMax debe bajar 30%-50% hasta que el valor de conversion funcione. Los asset groups `Claude` y `Estandar` no son suficientes para tomar decisiones por producto/margen.

Prioridad nueva: corregir medicion MX junto con Bali Lovense y Uva Ecuador antes de tomar decisiones de escalamiento.

## Addendum 2026-07-07 - WhatsApp vs WooCommerce MX

Aclaracion importante: las conversiones Google Ads con valor 0 en MX corresponden a conversaciones de WhatsApp. Eso es correcto si la conversacion no representa ingreso inmediato. La venta posterior vive en WooCommerce, asi que la lectura no debe hacerse con `conversion_value` de Google sino con un cruce WhatsApp -> ventas reales.

Archivo bruto del cruce: `data/mx_sales_ads_correlation_2026-07-07.json`.

Periodo 2026-06-01 a 2026-07-06:

- Gasto Google Ads MX: 25.078,18 MXN.
- Conversiones WhatsApp Google Ads: 65.
- Ventas WooCommerce MX: 75.655,55 MXN.
- Ordenes WooCommerce: 110.
- Unidades: 133.
- ROAS blended contra WooCommerce, sin atribucion fina: 3,02x.
- Ventas por categoria: Copa menstrual 56.576,55 MXN; Disco menstrual 19.079,00 MXN.

Lectura corregida:

El problema no es que el value 0 este mal configurado por si solo. El problema es que Google esta optimizando a conversaciones y Axis/Ads no estan cerrando el loop con ventas reales. Si no se importa el cierre de WhatsApp o no se cruza con WooCommerce por dia/campana, Google solo sabe conseguir conversaciones, no necesariamente ventas rentables.

La baja de Mexico existe, pero no es uniforme: hay dias con buen retorno blended, como 2026-06-04, 2026-06-08, 2026-06-17, 2026-06-27, 2026-07-06. Tambien hay dias claramente flojos o con gasto sin venta suficiente: 2026-06-05, 2026-06-13, 2026-06-20, 2026-06-21, 2026-07-05.

Acciones nuevas para MX:

- Crear un KPI operativo diario: `ventas WooCommerce / conversaciones WhatsApp` y `ventas WooCommerce / gasto Google`, no solo CPA WhatsApp.
- Si WhatsApp sigue como conversion primaria, asignar un valor esperado por conversacion segun tasa historica de cierre y ticket promedio, o importar cierres offline cuando se cierre la venta.
- Separar Search Brand/Categoria/Competencia para saber que conversaciones terminan en orden; hoy PMax y Search quedan mezclados con la venta final en WooCommerce.
- Revisar calidad de conversaciones de PMax: genera mas WhatsApps que Search, pero sin identificador de cierre no sabemos si vende mejor o solo trae curiosos.
- Usar los productos vendidos reales para alimentar el plan: Copa menstrual sigue liderando, pero Disco aporta 25% de ventas aproximadamente y no deberia quedar invisible en una cuenta tratada solo como `copa-menstrual`.

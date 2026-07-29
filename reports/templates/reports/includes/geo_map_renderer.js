function geoNormalizeKey(value){
  var raw=String(value||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
  var key=raw.replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"");
  var aliases={"bogota-d-c":"bogota","bogota-dc":"bogota","distrito-capital":"bogota","capital-district":"bogota","bogota-capital-district":"bogota","distrito-especial":"bogota","mexico-city":"distrito-federal","ciudad-de-mexico":"distrito-federal","cdmx":"distrito-federal","coahuila":"coahuila-de-zaragoza","estado-de-mexico":"mexico","edomex":"mexico","santo-domingo":"santo-domingo-de-los-tsachilas"};
  return aliases[key]||key;
}
function safeJsonParse(value,fallback){try{return JSON.parse(value||"");}catch(error){return fallback;}}
function geoNumber(value){var n=Number(value||0);return Number.isFinite(n)?n:0;}
function geoFullNumber(value){return new Intl.NumberFormat("es-CO",{maximumFractionDigits:0}).format(geoNumber(value));}
function geoMoney(value){return new Intl.NumberFormat("es-CO",{style:"currency",currency:"COP",maximumFractionDigits:0}).format(geoNumber(value));}
function geoEscape(value){var map={"&":"&amp;","<":"&lt;",">":"&gt;"};return String(value||"").replace(/[&<>]/g,function(ch){return map[ch]||ch;});}
function flattenGeoPoints(input,output){output=output||[];if(!Array.isArray(input)){return output;}if(typeof input[0]==="number"&&typeof input[1]==="number"){output.push(input);return output;}input.forEach(function(item){flattenGeoPoints(item,output);});return output;}
function geoFeatureName(feature){var props=feature&&feature.properties?feature.properties:{};return props.name||props.shapeName||props.NAME_1||props.name_local||"Region";}
function geoPathFromGeometry(geometry,project){
  if(!geometry){return " ";}
  function ringPath(ring){var d=[];ring.forEach(function(point,index){var p=project(point);d.push((index?"L":"M")+p[0].toFixed(1)+" "+p[1].toFixed(1));});return d.join(" ")+" Z";}
  if(geometry.type==="Polygon"){return (geometry.coordinates||[]).map(ringPath).join(" ");}
  if(geometry.type==="MultiPolygon"){var parts=[];(geometry.coordinates||[]).forEach(function(poly){poly.forEach(function(ring){parts.push(ringPath(ring));});});return parts.join(" ");}
  return " ";
}
function geoCentroid(geometry,project){var points=flattenGeoPoints((geometry&&geometry.coordinates)||[]);if(!points.length){return [380,310];}var x=0;var y=0;points.forEach(function(point){x+=point[0];y+=point[1];});return project([x/points.length,y/points.length]);}
function geoColor(metric,maxImpressions){var impressions=geoNumber(metric&&metric.impressions);if(!impressions||!maxImpressions){return "rgba(18, 30, 46, .92)";}var ratio=Math.max(.08,Math.min(1,impressions/maxImpressions));var light=18+ratio*44;return "hsl(181 72% "+light+"%)";}
function geoTooltipHtml(title,metric){metric=metric||{};var rows=[["Impresiones",geoFullNumber(metric.impressions)],["Reach/Vistas",geoFullNumber(metric.reach)],["Clics",geoFullNumber(metric.clicks)],["Compras",geoFullNumber(metric.purchases)],["Valor conversion",geoMoney(metric.conversion_value)],["Gasto",geoMoney(metric.spend)]];var html="<div class=\"geo-tooltip-title\">"+geoEscape(title)+"</div><div class=\"geo-tooltip-grid\">";rows.forEach(function(row){html+="<span class=\"geo-tooltip-label\">"+row[0]+"</span><span class=\"geo-tooltip-value\">"+row[1]+"</span>";});return html+"</div>";}
function geoEnsureMapChrome(card){var canvas=card.querySelector(".geo-map-canvas-real")||card;var controls=canvas.querySelector("[data-geo-controls]");if(!controls){controls=document.createElement("div");controls.className="geo-map-controls";controls.dataset.geoControls="true";controls.innerHTML="<button type=\"button\" data-geo-zoom=\"in\" aria-label=\"Acercar mapa\">+</button><button type=\"button\" data-geo-zoom=\"out\" aria-label=\"Alejar mapa\">-</button><button type=\"button\" data-geo-zoom=\"reset\" aria-label=\"Restablecer mapa\">Reset</button>";canvas.appendChild(controls);}var tooltip=canvas.querySelector("[data-geo-tooltip]");if(!tooltip){tooltip=document.createElement("div");tooltip.className="geo-map-tooltip";tooltip.dataset.geoTooltip="true";canvas.appendChild(tooltip);}return {canvas:canvas,controls:controls,tooltip:tooltip};}
function geoPositionTooltip(card,event){var canvas=card.querySelector(".geo-map-canvas-real")||card;var tooltip=canvas.querySelector("[data-geo-tooltip]");if(!tooltip){return;}var rect=canvas.getBoundingClientRect();var width=tooltip.offsetWidth||240;var height=tooltip.offsetHeight||120;var x=event.clientX-rect.left+14;var y=event.clientY-rect.top+14;if(x+width>rect.width-10){x=event.clientX-rect.left-width-14;}if(y+height>rect.height-10){y=event.clientY-rect.top-height-14;}tooltip.style.left=Math.max(8,x)+"px";tooltip.style.top=Math.max(8,y)+"px";}
function geoShowTooltip(card,event,title,metric){var canvas=card.querySelector(".geo-map-canvas-real")||card;var tooltip=canvas.querySelector("[data-geo-tooltip]");if(!tooltip){return;}tooltip.innerHTML=geoTooltipHtml(title,metric);tooltip.classList.add("is-visible");geoPositionTooltip(card,event);}
function geoHideTooltip(card){var canvas=card.querySelector(".geo-map-canvas-real")||card;var tooltip=canvas.querySelector("[data-geo-tooltip]");if(tooltip){tooltip.classList.remove("is-visible");}}
function geoApplyTransform(state){state.regionLayer.setAttribute("transform","translate("+state.x.toFixed(1)+" "+state.y.toFixed(1)+") scale("+state.scale.toFixed(3)+")");geoRescaleMarkers(state);}
function geoClampPan(state){var extra=(state.scale-1)*Math.max(state.width,state.height)*.48;state.x=Math.max(-extra,Math.min(extra,state.x));state.y=Math.max(-extra,Math.min(extra,state.y));}
function geoZoomAt(state,nextScale,cx,cy){var previous=state.scale;var next=Math.max(1,Math.min(5,nextScale));if(next===previous){return;}state.x=cx-(cx-state.x)*(next/previous);state.y=cy-(cy-state.y)*(next/previous);state.scale=next;if(next===1){state.x=0;state.y=0;}geoClampPan(state);geoApplyTransform(state);}
function geoRescaleMarkers(state){
  var occupied=[];
  var zoom=state.scale;
  state.markers.forEach(function(marker,index){
    var sx=state.x+marker.cx*zoom;
    var sy=state.y+marker.cy*zoom;
    var radius=Math.max(4,Math.min(22,marker.baseRadius*(.95-.1*Math.log2(Math.max(zoom,1)))));
    var visible=sx>-40&&sx<state.width+40&&sy>-40&&sy<state.height+40;
    marker.circle.setAttribute("cx",sx.toFixed(1));
    marker.circle.setAttribute("cy",sy.toFixed(1));
    marker.circle.setAttribute("r",radius.toFixed(1));
    marker.circle.setAttribute("stroke-width",Math.max(1.4,2.2-(zoom-1)*.18).toFixed(2));
    marker.circle.setAttribute("opacity",visible?"1":"0");
    if(marker.pulse){
      marker.pulse.setAttribute("cx",sx.toFixed(1));
      marker.pulse.setAttribute("cy",sy.toFixed(1));
      marker.pulse.setAttribute("r",(radius+4).toFixed(1));
      marker.pulse.setAttribute("opacity",visible&&zoom<3.2?".9":"0");
    }
    if(marker.hit){
      marker.hit.setAttribute("cx",sx.toFixed(1));
      marker.hit.setAttribute("cy",sy.toFixed(1));
      marker.hit.setAttribute("r",Math.max(18,radius+8).toFixed(1));
      marker.hit.setAttribute("opacity",visible?"0":"0");
    }
    if(marker.label){
      var minRank=zoom<1.45?5:zoom<2.2?9:999;
      var show=visible&&(index<minRank||marker.baseRadius>16||zoom>2.7);
      var directions=[[1,-.2],[1,.75],[-1,-.2],[-1,.75],[.25,-1.05],[.25,1.35]];
      var dir=directions[index%directions.length];
      var font=Math.max(8,Math.min(13,11.8-(zoom-1)*.45+(marker.baseRadius>16?1.1:0)));
      var lx=sx+dir[0]*(radius+8);
      var ly=sy+dir[1]*(radius+7);
      var estimatedWidth=Math.max(42,String(marker.name||"").length*font*.58);
      var box={x:dir[0]<0?lx-estimatedWidth:lx,y:ly-font,w:estimatedWidth,h:font+5};
      var collides=occupied.some(function(prev){return !(box.x+box.w<prev.x||prev.x+prev.w<box.x||box.y+box.h<prev.y||prev.y+prev.h<box.y);});
      if(collides&&zoom<2.4){show=false;}
      if(show){occupied.push(box);}
      marker.label.setAttribute("x",lx.toFixed(1));
      marker.label.setAttribute("y",ly.toFixed(1));
      marker.label.setAttribute("text-anchor",dir[0]<0?"end":"start");
      marker.label.setAttribute("font-size",font.toFixed(1));
      marker.label.setAttribute("opacity",show?"1":"0");
    }
  });
}
function geoWireControls(card,svg,controls,canvas,state){
  geoApplyTransform(state);
  function pointFromEvent(event){var rect=svg.getBoundingClientRect();return {x:(event.clientX-rect.left)*(state.width/Math.max(rect.width,1)),y:(event.clientY-rect.top)*(state.height/Math.max(rect.height,1))};}
  controls.querySelectorAll("[data-geo-zoom]").forEach(function(button){button.onclick=function(event){event.preventDefault();var action=button.dataset.geoZoom;var center={x:state.width/2,y:state.height/2};if(action==="reset"){geoZoomAt(state,1,center.x,center.y);return;}geoZoomAt(state,state.scale+(action==="in"?0.42:-0.42),center.x,center.y);};});
  svg.addEventListener("wheel",function(event){event.preventDefault();var p=pointFromEvent(event);var step=event.deltaY<0?1.18:.84;geoZoomAt(state,state.scale*step,p.x,p.y);},{passive:false});
  svg.onpointerdown=function(event){if(event.button!==0){return;}state.dragging=true;state.startX=event.clientX;state.startY=event.clientY;state.baseX=state.x;state.baseY=state.y;if(svg.setPointerCapture){svg.setPointerCapture(event.pointerId);}canvas.classList.add("is-panning");geoHideTooltip(card);};
  svg.onpointermove=function(event){if(!state.dragging){return;}state.x=state.baseX+event.clientX-state.startX;state.y=state.baseY+event.clientY-state.startY;geoClampPan(state);geoApplyTransform(state);};
  function stopPan(event){if(!state.dragging){return;}state.dragging=false;if(svg.releasePointerCapture){svg.releasePointerCapture(event.pointerId);}canvas.classList.remove("is-panning");}
  svg.onpointerup=stopPan;svg.onpointercancel=stopPan;svg.onpointerleave=stopPan;
}
async function renderGeoMap(card){
  var svg=card.querySelector("[data-geo-svg]");var loading=card.querySelector("[data-geo-loading]");if(!svg||!card.dataset.mapUrl){return;}
  var chrome=geoEnsureMapChrome(card);var regions=safeJsonParse(card.dataset.regions,[]);var points=safeJsonParse(card.dataset.points,[]);
  var metricByKey=new Map();regions.forEach(function(item){metricByKey.set(geoNormalizeKey(item.key||item.name),item);});
  var pointByKey=new Map();points.forEach(function(item){pointByKey.set(geoNormalizeKey(item.key||item.name),item);});
  var maxImpressions=1;regions.forEach(function(item){maxImpressions=Math.max(maxImpressions,geoNumber(item.impressions));});
  var maxPurchases=1;points.forEach(function(item){maxPurchases=Math.max(maxPurchases,geoNumber(item.purchases));});
  try{
    var response=await fetch(card.dataset.mapUrl,{cache:"force-cache"});if(!response.ok){throw new Error("HTTP "+response.status);}
    var geojson=await response.json();var features=geojson.features||[];var allPoints=flattenGeoPoints(features.map(function(feature){return feature.geometry&&feature.geometry.coordinates;}));
    var xs=allPoints.map(function(point){return point[0];});var ys=allPoints.map(function(point){return point[1];});
    var minX=Math.min.apply(null,xs);var maxX=Math.max.apply(null,xs);var minY=Math.min.apply(null,ys);var maxY=Math.max.apply(null,ys);
    var width=760;var height=620;var padding=22;var scale=Math.min((width-padding*2)/Math.max(maxX-minX,.01),(height-padding*2)/Math.max(maxY-minY,.01));
    var offsetX=(width-(maxX-minX)*scale)/2;var offsetY=(height-(maxY-minY)*scale)/2;function project(point){return [offsetX+(point[0]-minX)*scale,offsetY+(maxY-point[1])*scale];}
    svg.textContent=" ";var regionLayer=document.createElementNS("http://www.w3.org/2000/svg","g");var pulseLayer=document.createElementNS("http://www.w3.org/2000/svg","g");var pointLayer=document.createElementNS("http://www.w3.org/2000/svg","g");var labelLayer=document.createElementNS("http://www.w3.org/2000/svg","g");var hitLayer=document.createElementNS("http://www.w3.org/2000/svg","g");
    svg.appendChild(regionLayer);svg.appendChild(pulseLayer);svg.appendChild(pointLayer);svg.appendChild(labelLayer);
    svg.appendChild(hitLayer);
    var markers=[];var state={scale:1,x:0,y:0,width:width,height:height,regionLayer:regionLayer,markers:markers,dragging:false,startX:0,startY:0,baseX:0,baseY:0};
    features.forEach(function(feature){
      var name=geoFeatureName(feature);var key=geoNormalizeKey(name);var metric=metricByKey.get(key)||{};var path=document.createElementNS("http://www.w3.org/2000/svg","path");
      path.setAttribute("d",geoPathFromGeometry(feature.geometry,project));path.setAttribute("class","geo-real-region"+(metric.impressions?"":" geo-real-empty"));path.setAttribute("fill",geoColor(metric,maxImpressions));
      var opacity=metric.impressions?String(.28+Math.min(.67,geoNumber(metric.impressions)/maxImpressions*.67)):"0.74";path.setAttribute("fill-opacity",opacity);path.setAttribute("stroke","rgba(244,251,255,.32)");path.setAttribute("stroke-width","0.75");
      path.addEventListener("mouseenter",function(event){geoShowTooltip(card,event,name,metric);});path.addEventListener("mousemove",function(event){geoPositionTooltip(card,event);});path.addEventListener("mouseleave",function(){geoHideTooltip(card);});regionLayer.appendChild(path);
      var pointMetric=pointByKey.get(key);if(pointMetric&&geoNumber(pointMetric.purchases)>0){
        var center=geoCentroid(feature.geometry,project);var purchases=geoNumber(pointMetric.purchases);var radius=5+Math.sqrt(purchases/maxPurchases)*20;
        var pulse=document.createElementNS("http://www.w3.org/2000/svg","circle");pulse.setAttribute("class","geo-real-point-pulse");pulseLayer.appendChild(pulse);
        var circle=document.createElementNS("http://www.w3.org/2000/svg","circle");circle.setAttribute("class","geo-real-point");pointLayer.appendChild(circle);
        var hit=document.createElementNS("http://www.w3.org/2000/svg","circle");hit.setAttribute("class","geo-real-hit");hit.addEventListener("mouseenter",function(event){geoShowTooltip(card,event,pointMetric.name||name,pointMetric);});hit.addEventListener("mousemove",function(event){geoPositionTooltip(card,event);});hit.addEventListener("mouseleave",function(){geoHideTooltip(card);});hitLayer.appendChild(hit);
        var label=document.createElementNS("http://www.w3.org/2000/svg","text");label.setAttribute("class","geo-real-label");label.textContent=pointMetric.name;labelLayer.appendChild(label);
        markers.push({circle:circle,pulse:pulse,hit:hit,label:label,cx:center[0],cy:center[1],baseRadius:radius,name:pointMetric.name||name,purchases:purchases});
      }
    });
    markers.sort(function(a,b){return b.purchases-a.purchases;});
    geoWireControls(card,svg,chrome.controls,chrome.canvas,state);if(loading){loading.classList.add("is-hidden");}
  }catch(error){if(loading){loading.textContent="No se pudo cargar el mapa geografico.";}}
}
function setupGeoMaps(){document.querySelectorAll("[data-geo-map]").forEach(function(card){renderGeoMap(card);});}

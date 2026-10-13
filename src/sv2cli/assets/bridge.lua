-- sv2cli official-API bridge. No evaluation of arbitrary code or shell calls.
function getClientInfo()
  return {name="sv2cli bridge", author="White-Wolf-233", versionNumber=1,
          minEditorVersion=131329, category="sv2cli"}
end
local function path(name) return MAILBOX.."/"..name end
local function read(name)
  local f=io.open(path(name),"rb")
  if not f then return nil end
  local text=f:read("*a");f:close();return text
end
local function write(name, value)
  local temporary=path(name..".tmp")
  local f=assert(io.open(temporary,"wb"));f:write(json.encode(value));f:close()
  assert(os.rename(temporary,path(name)))
end
local function reference(a)
  local p=SV:getProject()
  local ti=a.track or 1
  assert(type(ti)=="number" and ti%1==0 and ti>=1 and ti<=p:getNumTracks(),"Track index out of range")
  local t=p:getTrack(ti)
  local gi=a.group or 1
  assert(type(gi)=="number" and gi%1==0 and gi>=1 and gi<=t:getNumGroups(),"Group index out of range")
  return t:getGroupReference(gi)
end
local methods={}
methods["host.info"]=function() return SV:getHostInfo() end
methods["project.summary"]=function()
  local p=SV:getProject();local tracks={}
  for i=1,p:getNumTracks() do
    local t=p:getTrack(i)
    tracks[#tracks+1]={index=i,name=t:getName(),groups=t:getNumGroups()}
  end
  return {file=p:getFileName(),duration=p:getDuration(),tracks=tracks}
end
methods["notes.list"]=function(a)
  local r=reference(a);local g=r:getTarget();local notes={}
  for i=1,g:getNumNotes() do
    local n=g:getNote(i)
    notes[#notes+1]={index=i,onset=n:getOnset()+r:getTimeOffset(),duration=n:getDuration(),
      pitch=n:getPitch()+r:getPitchOffset(),lyrics=n:getLyrics(),phonemes=n:getPhonemes()}
  end
  return {notes=notes}
end
methods["computed.phonemes"]=function(a)
  local r=reference(a)
  return {phonemes=SV:getPhonemesForGroup(r),attributes=SV:getComputedAttributesForGroup(r)}
end
methods["computed.pitch"]=function(a)
  assert(type(a.start)=="number" and type(a.interval)=="number" and a.interval>0,"start and interval required")
  assert(type(a.frames)=="number" and a.frames%1==0 and a.frames>0 and a.frames<=100000,"frames must be 1..100000")
  return {pitch=SV:getComputedPitchForGroup(reference(a),a.start,a.interval,a.frames)}
end
methods["playback.status"]=function()
  local p=SV:getPlayback();return {status=p:getStatus(),playhead=p:getPlayhead()}
end
for _,name in ipairs({"play","stop","pause"}) do
  methods["playback."..name]=function() local p=SV:getPlayback();p[name](p);return {done=true} end
end
methods["playback.seek"]=function(a)
  assert(type(a.seconds)=="number" and a.seconds>=0,"seconds must be nonnegative")
  SV:getPlayback():seek(a.seconds);return {done=true}
end
local function note(a)
  local g=reference(a):getTarget();local index=a.note or 1
  assert(type(index)=="number" and index%1==0 and index>=1 and index<=g:getNumNotes(),"Note index out of range")
  return g:getNote(index)
end
methods["retake.generate"]=function(a)
  assert(a.expectedProject and a.expectedProject~="","Retake mutation requires expectedProject")
  local n=note(a);SV:getProject():newUndoRecord()
  local result=n:getRetakes():generateTake(a.duration==true,a.pitch==true,a.timbre==true)
  return {result=result}
end
methods["retake.activate"]=function(a)
  assert(a.expectedProject and a.expectedProject~="","Retake mutation requires expectedProject")
  assert(type(a.id)=="number","take id required")
  local n=note(a);SV:getProject():newUndoRecord();n:getRetakes():setActiveTake(a.id);return {done=true}
end
local function poll()
  local text=read("request.json")
  if text then
    local ok,request=pcall(json.decode,text)
    if ok and type(request)=="table" and type(request.id)=="string" and request.id:match("^[a-f0-9]+$") then
      os.remove(path("request.json"))
      local success,value=pcall(function()
        assert(request.expiresAt and os.time()<=request.expiresAt,"Request expired")
        assert(methods[request.method],"Unsupported method")
        if request.expectedProject then
          assert(SV:getProject():getFileName()==request.expectedProject,"Active project does not match expectedProject")
        end
        local a=request.args or {};a.expectedProject=request.expectedProject
        return methods[request.method](a)
      end)
      local reply={id=request.id,ok=success}
      if success then reply.result=value else reply.error=tostring(value) end
      pcall(write,"response-"..request.id..".json",reply)
    end
  end
  SV:setTimeout(100,poll)
end
function main() poll() end

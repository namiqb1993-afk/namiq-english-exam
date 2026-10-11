import os, json, uuid, random, secrets, hashlib, hmac, urllib.request, datetime, csv, io, threading, time
from collections import defaultdict
from flask import Flask, jsonify, request, abort, session, send_from_directory, Response
from sqlalchemy import create_engine, text

BASE=os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE,'content.json'),encoding='utf-8') as f: BANK=json.load(f)
app=Flask(__name__,static_folder='static')
AUDIO_DIR=os.path.join(BASE,'static','audio')
os.makedirs(AUDIO_DIR,exist_ok=True)
app.secret_key=os.getenv('SESSION_SECRET') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('REPLIT_DEPLOYMENT')=='1',MAX_CONTENT_LENGTH=2*1024*1024)
DB=os.getenv('DATABASE_URL','sqlite:///'+os.path.join(BASE,'development.db'))
if DB.startswith('postgres://'):DB=DB.replace('postgres://','postgresql+psycopg://',1)
if DB.startswith('postgresql://'):DB=DB.replace('postgresql://','postgresql+psycopg://',1)
engine=create_engine(DB,pool_pre_ping=True)
with engine.begin() as c:
 c.execute(text('CREATE TABLE IF NOT EXISTS attempts (id VARCHAR(36) PRIMARY KEY, student_key VARCHAR(80), first_name VARCHAR(100), last_name VARCHAR(100), created_at VARCHAR(50), submitted_at VARCHAR(50), exam_json TEXT, answers_json TEXT, score_objective FLOAT, essay_score FLOAT, essay_approved INTEGER DEFAULT 0, token_hash VARCHAR(100), email_status VARCHAR(30) DEFAULT :p)'),{'p':'pending'})

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
def check_teacher():return session.get('teacher') is True
def teacher_only():
 if not check_teacher():abort(403)
def rowdict(r):return dict(r._mapping) if r else None
def getattempt(id):
 with engine.connect() as c:return rowdict(c.execute(text('SELECT * FROM attempts WHERE id=:i'),{'i':id}).first())
def hash_token(t):return hashlib.sha256(t.encode()).hexdigest()
def owns(row):return check_teacher() or (request.headers.get('X-Attempt-Token') and hmac.compare_digest(row['token_hash'],hash_token(request.headers['X-Attempt-Token'])))
def public_question(q):return {k:v for k,v in q.items() if k not in ('answer','explanation','transcript','source')}
def build():
 # Balance by topic, prefer least-recently-used for the student at API layer.
 groups=defaultdict(list)
 for q in BANK['grammar']:groups[q['topic']].append(q)
 topiclist=list(groups);random.shuffle(topiclist)
 picked=[]
 while len(picked)<13:
  random.shuffle(topiclist)
  for t in topiclist:
   if len(picked)>=13:break
   possible=[x for x in groups[t] if x['id'] not in {p['id'] for p in picked}]
   if possible:picked.append(random.choice(possible))
 if len(picked)!=13:raise ValueError('Not enough approved grammar questions')
 listening=random.choice(BANK['listenings'])
 readings=random.sample(BANK['readings'],2)
 essay=random.choice(BANK['essays'])
 def make(q,sec):return {**q,'section':sec,'type':'tf4' if q.get('type')=='tf' else 'single'}
 questions=[make(q,'grammar') for q in picked]
 questions += [make(q,'listening') for q in listening['q']]
 for no,r in enumerate(readings):questions += [make(q,'reading'+str(no+1)) for q in r['q']]
 questions.append({'section':'essay','type':'essay','id':'ESSAY-'+str(BANK['essays'].index(essay)),'q':essay})
 assert len(questions)==26
 return {'questions':questions,'listening':listening,'readings':readings,'essay':essay}
def view(exam,submitted=False):
 result={'questions':[public_question(q) for q in exam['questions']], 'readings':[{k:v for k,v in r.items() if k!='q'} for r in exam['readings']], 'listening':{'title':exam['listening']['title']},'audio_available':bool(exam['listening'].get('audio'))}
 if exam['listening'].get('audio'):result['listening']['audio_url']='/static/audio/'+exam['listening']['audio']
 if submitted:result['listening']['transcript']=exam['listening']['transcript']
 return result

def score(exam,answers):
 details=[];earned=0
 for i,q in enumerate(exam['questions'][:25]):
  answer=answers[i] if i<len(answers) else None
  correct=q.get('answer');value=0
  if q['type']=='tf4':
   if isinstance(answer,list) and len(answer)==4:
    hits=sum(str(a).lower()==str(b).lower() for a,b in zip(answer,correct))
    value=1 if hits==4 else .5 if hits==3 else 0
  else:
   if isinstance(answer,(int,str)) and str(answer).strip().upper()==str(correct).strip().upper():value=1
  earned+=value
  details.append({'number':i+1,'answer':answer,'correct_answer':correct,'raw':value,'max':1,'explanation':q.get('explanation','Düzgün cavabı yoxlayın.'),'section':q['section']})
 return round(earned/25*80,2),details

def notify(id):
 row=getattempt(id)
 key=os.getenv('RESEND_API_KEY');sender=os.getenv('EMAIL_FROM');to=os.getenv('TEACHER_EMAIL','namiq.b1993@gmail.com')
 status='not_configured'
 if key and sender:
  exam=json.loads(row['exam_json']); answers=json.loads(row['answers_json']);_,details=score(exam,answers)
  body=f"Şagird: {row['first_name']} {row['last_name']}\nİmtahan: {id}\nTarix: {row['submitted_at']}\nObyektiv bal: {row['score_objective']}/80\nEsse: müəllim təsdiqini gözləyir\n\nEsse:\n{answers[25]}\n\n"
  for d in details:body+=f"{d['number']}. Cavab: {d['answer']} | Düzgün: {d['correct_answer']} | Bal: {d['raw']}\n"
  body+=f"\nMüəllim paneli: {os.getenv('PUBLIC_BASE_URL','(dashboard URL təyin edilməyib)')}/teacher"
  data=json.dumps({'from':sender,'to':[to],'subject':f'DİM sınağı: {row["first_name"]} {row["last_name"]}','text':body}).encode()
  try:
   req=urllib.request.Request('https://api.resend.com/emails',data=data,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
   with urllib.request.urlopen(req,timeout=12) as r:status='sent' if r.status<300 else 'failed'
  except Exception:status='failed'
 with engine.begin() as c:c.execute(text('UPDATE attempts SET email_status=:s WHERE id=:i'),{'s':status,'i':id})

@app.errorhandler(404)
def not_found(err):return jsonify(error='Məlumat tapılmadı'),404
@app.errorhandler(403)
def forbidden(err):return jsonify(error='Giriş qadağandır'),403
@app.errorhandler(500)
def internal_error(err):return jsonify(error='Server xətası baş verdi'),500
@app.get('/health')
def health():return jsonify(status='ok',grammar_count=len(BANK['grammar']),audio_count=sum(bool(x.get('audio')) for x in BANK['listenings']))
@app.get('/')
def home():return send_from_directory('static','index.html')
@app.get('/teacher')
def teacher():return send_from_directory('static','teacher.html')
@app.post('/api/start')
def start():
 d=request.get_json(silent=True) or {};fn=str(d.get('first_name','')).strip()[:100];ln=str(d.get('last_name','')).strip()[:100]
 if len(fn)<2 or len(ln)<2:return jsonify(error='Ad və soyad minimum 2 hərf olmalıdır.'),400
 # Use a coarse name key; students can share names, so reuse avoidance is best-effort only.
 key=hashlib.sha256((fn+'|'+ln).casefold().encode()).hexdigest()[:80]
 with engine.connect() as c: previous=c.execute(text('SELECT exam_json FROM attempts WHERE student_key=:k ORDER BY created_at DESC LIMIT 6'),{'k':key}).fetchall()
 used=set()
 for p in previous:
  try:used.update(x['id'] for x in json.loads(p[0])['questions'][:13])
  except Exception:pass
 exam=build();unused=[x for x in BANK['grammar'] if x['id'] not in used and x['id'] not in {q['id'] for q in exam['questions'][:13]}]
 random.shuffle(unused)
 for i,q in enumerate(exam['questions'][:13]):
  if q['id'] in used:
   replacement=next((r for r in unused if r['topic']==q['topic']),None)
   if replacement:
    exam['questions'][i]={**replacement,'section':'grammar','type':'tf4' if q.get('type')=='tf' else 'single'};unused.remove(replacement)
 id=str(uuid.uuid4());token=secrets.token_urlsafe(32)
 with engine.begin() as c:c.execute(text('INSERT INTO attempts (id,student_key,first_name,last_name,created_at,exam_json,answers_json,token_hash,email_status) VALUES (:i,:k,:f,:l,:d,:e,:a,:t,:s)'),{'i':id,'k':key,'f':fn,'l':ln,'d':now(),'e':json.dumps(exam,ensure_ascii=False),'a':json.dumps([None]*26),'t':hash_token(token),'s':'pending'})
 return jsonify(id=id,token=token,first_name=fn,last_name=ln,exam=view(exam))
@app.route('/api/attempt/<id>',methods=['GET','PATCH'])
def attempt(id):
 row=getattempt(id)
 if not row:abort(404)
 if not owns(row):abort(403)
 if request.method=='PATCH':
  if row['submitted_at']:return jsonify(error='İmtahan artıq təhvil verilib.'),409
  a=(request.get_json(silent=True) or {}).get('answers')
  if not isinstance(a,list) or len(a)!=26:return jsonify(error='26 cavab tələb olunur'),400
  a=[str(x)[:3000] if x is not None and not isinstance(x,list) else x for x in a]
  with engine.begin() as c:c.execute(text('UPDATE attempts SET answers_json=:a WHERE id=:i AND submitted_at IS NULL'),{'a':json.dumps(a,ensure_ascii=False),'i':id})
  return jsonify(saved=True)
 exam=json.loads(row['exam_json']);ans=json.loads(row['answers_json'])
 data={'id':id,'first_name':row['first_name'],'last_name':row['last_name'],'exam':view(exam, bool(row['submitted_at'])),'answers':ans,'submitted':bool(row['submitted_at'])}
 if row['submitted_at']:
  value,details=score(exam,ans);data.update(objective_score=value,essay_score=row['essay_score'],approved=bool(row['essay_approved']),details=details,total=round(value+(row['essay_score'] or 0),2) if row['essay_score'] is not None else None)
 return jsonify(data)
@app.post('/api/submit/<id>')
def submit(id):
 row=getattempt(id)
 if not row:abort(404)
 if not owns(row):abort(403)
 if row['submitted_at']:return jsonify(error='Artıq təhvil verilib'),409
 exam=json.loads(row['exam_json']);answers=json.loads(row['answers_json']);value,_=score(exam,answers)
 with engine.begin() as c:c.execute(text('UPDATE attempts SET submitted_at=:d,score_objective=:s WHERE id=:i AND submitted_at IS NULL'),{'d':now(),'s':value,'i':id})
 threading.Thread(target=notify,args=(id,),daemon=True).start()
 return jsonify(submitted=True,objective_score=value,provisional=True)
@app.post('/api/login')
def login():
 supplied=(request.get_json(silent=True) or {}).get('password','')
 expected=os.getenv('TEACHER_PASSWORD','')
 if len(expected)<12:return jsonify(error='TEACHER_PASSWORD ən azı 12 simvol olmalıdır.'),503
 if not hmac.compare_digest(str(supplied),expected):return jsonify(error='Şifrə yanlışdır'),401
 session.clear();session['teacher']=True;return jsonify(ok=True)
@app.post('/api/logout')
def logout():session.clear();return jsonify(ok=True)
@app.post('/api/admin/audio')
def upload_audio():
 teacher_only()
 file=request.files.get('audio')
 if not file or not file.filename.lower().endswith(('.mp3','.m4a','.wav','.ogg')):
  return jsonify(error='MP3, M4A, WAV və ya OGG faylı seçin'),400
 # Choose an existing listening title so the uploaded sound belongs to the passage
 title=request.form.get('title','')
 lesson=next((x for x in BANK['listenings'] if x['title']==title),None)
 if not lesson:return jsonify(error='Dinləmə mətni tapılmadı'),400
 extension=file.filename.rsplit('.',1)[-1].lower()
 name=secrets.token_hex(12)+'.'+extension
 file.save(os.path.join(AUDIO_DIR,name))
 lesson['audio']=name
 # Note: On ephemeral hosts this file may not survive redeploy; use persistent object storage for production.
 with open(os.path.join(BASE,'content.json'),'w',encoding='utf-8') as fh:json.dump(BANK,fh,ensure_ascii=False,indent=2)
 return jsonify(ok=True,audio_url='/static/audio/'+name)

@app.get('/api/admin/listenings')
def list_listenings():
 teacher_only()
 return jsonify([{'title':x['title'],'audio':x.get('audio')} for x in BANK['listenings']])

@app.get('/api/admin/submissions')
def submissions():
 teacher_only()
 with engine.connect() as c:rows=c.execute(text('SELECT id,first_name,last_name,created_at,submitted_at,score_objective,essay_score,essay_approved,email_status FROM attempts WHERE submitted_at IS NOT NULL ORDER BY submitted_at DESC LIMIT 1000')).mappings().all()
 return jsonify([dict(x) for x in rows])
@app.get('/api/admin/attempt/<id>')
def adminattempt(id):
 teacher_only();row=getattempt(id)
 if not row:abort(404)
 exam=json.loads(row['exam_json']);ans=json.loads(row['answers_json']);_,details=score(exam,ans)
 return jsonify(row={k:v for k,v in row.items() if k not in ('token_hash','exam_json','answers_json')},exam=exam,answers=ans,details=details)
@app.post('/api/admin/approve/<id>')
def approve(id):
 teacher_only();d=request.get_json(silent=True) or {};rubric=d.get('rubric')
 if not isinstance(rubric,list) or len(rubric)!=5:return jsonify(error='5 meyar üzrə bal yazın'),400
 limits=[5,5,4,3,3]
 try:points=[float(x) for x in rubric]
 except Exception:return jsonify(error='Rəqəm olmalıdır'),400
 if any(not 0<=p<=cap for p,cap in zip(points,limits)):return jsonify(error='Rubrika hədlərini yoxlayın'),400
 row=getattempt(id)
 if not row or not row['submitted_at']:abort(404)
 with engine.begin() as c:c.execute(text('UPDATE attempts SET essay_score=:s, essay_approved=1 WHERE id=:i'),{'s':sum(points),'i':id})
 return jsonify(ok=True,final=round(row['score_objective']+sum(points),2))
@app.get('/api/admin/export.csv')
def export():
 teacher_only()
 with engine.connect() as c:rows=c.execute(text('SELECT id,first_name,last_name,submitted_at,score_objective,essay_score,essay_approved,email_status FROM attempts WHERE submitted_at IS NOT NULL ORDER BY submitted_at DESC')).mappings().all()
 output=io.StringIO();fields=['id','first_name','last_name','submitted_at','score_objective','essay_score','essay_approved','email_status'];w=csv.DictWriter(output,fieldnames=fields);w.writeheader();w.writerows([dict(r) for r in rows]);return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="dim-results.csv"'})
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=False)

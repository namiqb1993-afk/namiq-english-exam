# Namiq Bağırlı — English Exam Platform | Server paketi

Bu **statik HTML deyil**. Şagird cavablarının serverdə saxlanması və e-poçt üçün Python hostinq, PostgreSQL və təsdiqli e-poçt göndəricisi lazımdır.

## Render üzərindən yerləşdirmə
1. ZIP-i açın və faylları GitHub repository-yə yükləyin.
2. Render.com → New → Blueprint → repository seçin. `render.yaml` server konfiqurasiyasıdır.
3. Davamlı PostgreSQL bazası yaradın və `DATABASE_URL` sirrinə həmin bağlantını əlavə edin.
4. `TEACHER_PASSWORD` (12+ simvol), `SESSION_SECRET`, `TEACHER_EMAIL=namiq.b1993@gmail.com` dəyişənlərini təyin edin.
5. E-poçt üçün Resend domenini təsdiqləyin, `RESEND_API_KEY` və `EMAIL_FROM` əlavə edin.
6. Sayt açıldıqdan sonra `/health`, `/`, `/teacher`, sınaq başlanması və nəticənin saxlanmasını yoxlayın.
7. Audio üçün müəllim panelində yükləmə bölməsi lokal işləyir; istehsalda davamlı media storage təchiz edilməyincə ona etibar etməyin.
8. İctimai linki yalnız tam yoxlamadan sonra paylaşın.

## Məhdudiyyətlər
- `content.json` daxilində yalnız müəllif tərəfindən yaradılmış 40 qrammatika sualı, 4 reading və 1 audio yazısı olmayan listening var. DİM kitabının original sualları aktiv deyil.
- Hər imtahan 26 sualdır, ancaq 1 listening olması səbəbilə o hissə fərqlənmir.
- Esse avtomatik qiymətləndirilmir; müəllim təsdiq edir.
- E-poçt servisi konfiqurasiya olunmadan işləmir.
- Bu, tam auditi, spam qoruması və DİM materialının yayımlanması hüquqları həll edilmiş yekun məhsul deyil.

## Run
İşçi qovluq: `app.py` yerləşən qovluq.
`pip install -r requirements.txt`
`python app.py`
`http://localhost:5000`

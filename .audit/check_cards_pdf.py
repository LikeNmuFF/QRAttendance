import sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'.venv/Lib/site-packages'))
sys.path.insert(0,str(root/'python'))
import fitz,cv2,numpy as np
from attendance import create_app
from attendance.db import get_db,replace_card,qr_payload
output=root/'.audit'
with tempfile.TemporaryDirectory() as directory:
    app=create_app(dict(TESTING=True,DATABASE=Path(directory)/'cards.db',ADMIN_PASSWORD='test-admin-password',ATTENDANCE_TOKEN='test-device-token',SECRET_KEY='test'))
    students=[('S1','Maria Dela Cruz'),('S2','Juan Santos'),('S3','Jos\u00e9 Mu\u00f1oz'),('W'*40,'W'*80),('S5','Ana Reyes'),('S6','Carlo Mendoza'),('S7','Isabel Cruz')]
    with app.app_context(),get_db() as db:
        for sid,name in students:
            db.execute('INSERT INTO students VALUES (?,?)',(sid,name))
            replace_card(sid)
        expected={sid:qr_payload(sid) for sid,name in students}
    client=app.test_client()
    with client.session_transaction() as session:
        session.update(admin=True,csrf='test')
    response=client.get('/students/cards.pdf')
    assert response.status_code==200
    (output/'new-student-cards.pdf').write_bytes(response.data)
    document=fitz.open(stream=response.data,filetype='pdf')
    assert len(document)==2,len(document)
    decoded=[]
    for n,page in enumerate(document):
        text=page.get_text()
        assert 'Page '+str(n+1)+' of 2' in text
        pix=page.get_pixmap(matrix=fitz.Matrix(3,3),alpha=False)
        pix.save(str(output/('new-student-cards-page-'+str(n+1)+'.png')))
        # Independently decode each QR from the rendered PDF at print resolution.
        for position in range(min(6,len(students)-n*6)):
            card_width=(page.rect.width-56-12)/2
            center=28+(position%2)*(card_width+12)+card_width/2
            top=52+(position//2)*256
            clip=fitz.Rect(center-56,top+28,center+56,top+140)
            qr=page.get_pixmap(matrix=fitz.Matrix(4,4),clip=clip,alpha=False)
            data=cv2.imdecode(np.frombuffer(qr.tobytes('png'),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
            payload,_,_=cv2.QRCodeDetector().detectAndDecode(data)
            assert payload,('undecodable PDF QR',n,position)
            decoded.append(payload)
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    x0,y0,x1,y1=span['bbox']
                    assert 0<=x0<x1<=page.rect.width and 0<=y0<y1<=page.rect.height,(span['text'],span['bbox'])
    assert set(decoded)==set(expected.values()),decoded
    all_text=''.join(page.get_text() for page in document)
    for sid,name in students:
        assert sid in all_text.replace('\n',''),sid
        assert name.replace(' ','') in all_text.replace('\n','').replace(' ',''),name
    single=client.get('/students/cards.pdf?mode=selected&student_id=S2&message=Bring+this+card+to+class.')
    single_doc=fitz.open(stream=single.data,filetype='pdf')
    text=single_doc[0].get_text()
    assert 'Juan Santos' in text and 'Maria Dela Cruz' not in text
    assert 'Bring this card to class.' in text
    print('PASS: A4 PDF, six cards/page, pagination, long/accented names, all seven rendered QR codes decode, individual selection and custom message')

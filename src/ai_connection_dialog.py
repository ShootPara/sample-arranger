"""Dedicated app connection setup; token never enters project/CLI request/logs."""
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,QFileDialog,QDialogButtonBox
from broker_port import configure,connection


class ConnectionDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('Local AI connection');self.resize(580,340)
        layout=QVBoxLayout(self);text=QLabel('Use the broker’s dedicated sample-arranger inference credential. Only brief text and compact musical features are sent. Audio, plugin state and catalog paths stay on this PC. The server chooses the model.');text.setWordWrap(True);layout.addWidget(text)
        form=QFormLayout();layout.addLayout(form);self.address=QLineEdit();self.address.setAccessibleName('AI broker HTTPS address');form.addRow('Broker address',self.address)
        self.ca=QLineEdit();self.ca.setAccessibleName('Broker trusted certificate authority file');form.addRow('CA certificate',self.ca)
        choose=QPushButton('Choose CA certificate…');choose.clicked.connect(self.choose_ca);form.addRow(choose)
        self.token=QLineEdit();self.token.setEchoMode(QLineEdit.EchoMode.Password);self.token.setAccessibleName('Dedicated sample-arranger inference token');form.addRow('App token',self.token)
        self.message=QLabel('The token is protected for this Windows user and stored outside projects/source. Existing coding keys are not imported.');self.message.setWordWrap(True);layout.addWidget(self.message)
        try:config=connection();self.address.setText(config['endpoint']);self.ca.setText(config['ca_file'] or '')
        except (OSError,ValueError):pass
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def choose_ca(self):
        path=QFileDialog.getOpenFileName(self,'Choose existing broker CA certificate',filter='Certificates (*.crt *.pem *.cer)')[0]
        if path:self.ca.setText(path)
    def save(self):
        try:configure(self.address.text().strip(),self.token.text(),self.ca.text().strip() or None)
        except (OSError,ValueError) as error:self.message.setText(str(error));return
        self.token.clear();self.accept()

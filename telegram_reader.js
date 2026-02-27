/**
 * AUTOMATIZADOR DE TELEGRAM COMPLETO (Node.js + Appium)
 *
 * Esta versión incluye logs limpios y una lógica de reseteo
 * mucho más robusta para evitar crashes entre números.
 *
 * **Integración de correcciones y mejoras esenciales sobre la base proporcionada:**
 * - **CORRECCIÓN: 'Malformed type for keycode'**: El `sendKeyEvent` ahora recibe un string ('67').
 * - **Solución al error de 'Unable to resolve launchable activity'**: Se elimina `appium:appActivity` para auto-detección.
 * - **Limpieza de datos de la app vía ADB**: Función `clearAppData` para asegurar un estado limpio (crucial con `noReset: true`).
 * - **Espera indefinida para el código SMS**: `waitForTelegramCode` sin timeout.
 * - **Robustez de la conexión y navegación**: Reintentos de conexión Appium, navegación robusta en Telegram.
 * - **Formato de resultados finales**: Incluye `deviceSerial`, `port`, `iccid` y maneja `UNKNOWN` status.
 * - **Limpieza de archivos temporales**: Elimina el archivo .txt del número en `numerosNode`.
 * - **Modo de prueba directo**: Permite ejecutar el script para un solo número/dispositivo.
 * - **Flujo de apertura/cierre de app optimizado**: Se intenta minimizar aperturas/cierres redundantes.
 */

const { remote } = require('webdriverio');
const fs = require('fs').promises;
const path = require('path');
const { exec } = require('child_process'); // Para ejecutar comandos ADB desde Node.js

// --- CONFIGURACIÓN ---
const APPIUM_OPTIONS = {
    path: '/',
    port: 4723,
    logLevel: 'error', // Cambiado de 'info' a 'error' para un tracking limpio.
    capabilities: {
        'platformName': 'Android',
        'appium:automationName': 'UiAutomator2',
        'appium:deviceName': 'Android',
        'appium:appPackage': 'org.telegram.messenger',
        // 'appium:appActivity': 'org.telegram.ui.LaunchActivity', // <-- ELIMINADO: Appium buscará la actividad principal por defecto
        'appium:noReset': true, // Asume que la app está preinstalada y no borra datos automáticamente
        'appium:skipUnlock': true, // Intenta desbloquear el dispositivo automáticamente.
        'appium:clearSystemFiles': true, // Limpia archivos de Appium en el dispositivo antes de la sesión.
        'appium:newCommandTimeout': 3600, // <-- AUMENTADO: Para permitir esperas indefinidas de códigos.
    }
};
const RESULTS_FILE = 'results.txt';
const CODE_FOLDER = 'numerosNode';
const POLLING_INTERVAL_MS = 2000; // Frecuencia de sondeo para el archivo de código
const TELEGRAM_PACKAGE_NAME = 'org.telegram.messenger'; // Nombre del paquete de Telegram

// --- FUNCIONES AUXILIARES ---

async function readSimData() {
    try {
        const filePath = path.join(__dirname, RESULTS_FILE);
        const data = await fs.readFile(filePath, 'utf-8');
        const lines = data.trim().split('\n');
        return lines.slice(1).map(line => {
            // Asegurarse de que el orden de los campos coincide con results.txt
            // Tu results.txt debería tener: phoneNumber, deviceSerial, iccid, port, timestamp
            const [phoneNumber, deviceSerial, iccid, port] = line.split(','); 
            return {
                phoneNumber: phoneNumber?.trim(),
                deviceSerial: deviceSerial?.trim(), 
                port: port?.trim(),
                iccid: iccid?.trim() || ''
            };
        }).filter(sim => sim.phoneNumber && sim.phoneNumber !== 'N/A_No_Number_Found');
    } catch (error) {
        console.error(`[ERROR] Error crítico al leer '${RESULTS_FILE}':`, error);
        return [];
    }
}

async function saveResult(simData, status) {
    const statusToFileMap = {
        '2FA': 'num_2fa.txt',
        'NO_2FA': 'num_no_2fa.txt',
        'SUSPENDED': 'num_suspendidos.txt',
        'TOO_MANY_ATTEMPTS': 'num_reintentos.txt',
        'UNKNOWN': 'num_error.txt' // <-- AÑADIDO: Guardar también los UNKNOWN/errores
    };
    const fileName = statusToFileMap[status];
    if (fileName) {
        const filePath = path.join(__dirname, fileName);
        // Guardado con formato completo: phoneNumber,port,iccid,deviceSerial
        const lineToWrite = `${simData.phoneNumber},${simData.port},${simData.iccid},${simData.deviceSerial}\n`; // <-- AÑADIDO: deviceSerial
        try {
            await fs.appendFile(filePath, lineToWrite);
            console.log(`[INFO][${simData.phoneNumber}] Resultado guardado en ${fileName} con COM, ICCID y DeviceSerial.`);
        } catch (error) {
            console.error(`[ERROR][${simData.phoneNumber}] Error al guardar el resultado en ${fileName}:`, error);
        }
    }
}

async function waitForTelegramCode(phoneNumber) {
    const codeFilePath = path.join(__dirname, CODE_FOLDER, `${phoneNumber}.txt`);
    console.log(`[INFO][${phoneNumber}] Esperando código en: ${codeFilePath} (espera indefinida)...`);
    
    while (true) { // <-- MODIFICADO: Bucle infinito sin timeout
        try {
            const code = await fs.readFile(codeFilePath, 'utf-8');
            if(code.trim()){
                console.log(`\n[INFO][${phoneNumber}] ¡ÉXITO! Código encontrado: ${code.trim()}`);
                return code.trim(); // Se borra el archivo en cleanupPhoneNumberFile
            }
        } catch (error) {
            if (error.code !== 'ENOENT') {
                 console.error(`\n[ERROR][${phoneNumber}] Error leyendo archivo de código:`, error);
            }
        }
        process.stdout.write(".");
        await new Promise(resolve => setTimeout(resolve, POLLING_INTERVAL_MS));
    }
}

// <-- NUEVA FUNCIÓN: Para limpiar el archivo de código después de usarlo
async function cleanupPhoneNumberFile(phoneNumber) {
    const codeFilePath = path.join(__dirname, CODE_FOLDER, `${phoneNumber}.txt`);
    try {
        await fs.access(codeFilePath); // Verifica si el archivo existe
        await fs.unlink(codeFilePath); // Elimina el archivo
        console.log(`[INFO][${phoneNumber}] Archivo '${phoneNumber}.txt' eliminado de ${CODE_FOLDER}.`);
    } catch (error) {
        if (error.code === 'ENOENT') {
            console.log(`[INFO][${phoneNumber}] Archivo '${phoneNumber}.txt' no encontrado en ${CODE_FOLDER} (ya eliminado o no existía).`);
        } else {
            console.error(`[ERROR][${phoneNumber}] Error al intentar eliminar el archivo '${phoneNumber}.txt':`, error);
        }
    }
}

// <-- NUEVA FUNCIÓN: Para limpiar los datos de la app usando ADB
async function clearAppData(deviceSerial, packageName) {
    console.log(`[INFO][${deviceSerial}] Limpiando datos de la app '${packageName}' via ADB...`);
    return new Promise((resolve, reject) => {
        exec(`adb -s ${deviceSerial} shell pm clear ${packageName}`, (error, stdout, stderr) => {
            if (error) {
                console.error(`[ERROR][${deviceSerial}] Error al limpiar datos de la app: ${error.message}`);
                reject(error);
                return;
            }
            if (stderr) {
                console.error(`[ERROR][${deviceSerial}] Stderr al limpiar datos de la app: ${stderr}`);
            }
            console.log(`[INFO][${deviceSerial}] Datos de la app '${packageName}' limpiados exitosamente.`);
            resolve(stdout);
        });
    });
}

// --- FUNCIÓN PRINCIPAL ---

async function main() {
    let simsToProcess = [];
    const args = process.argv.slice(2); 

    if (args.length >= 2) {
        // Modo de prueba directo: node telegram_reader.js <phoneNumber> <deviceSerial> [port] [iccid]
        const phoneNumber = args[0];
        const deviceSerial = args[1];
        const port = args[2] || 'COM_TEST'; 
        const iccid = args[3] || 'ICCID_TEST'; 

        simsToProcess.push({
            phoneNumber,
            deviceSerial,
            port,
            iccid
        });
        console.log(`[INFO] Modo de prueba directo activado para número: ${phoneNumber}, Dispositivo: ${deviceSerial}`);

        // Aseguramos que el directorio y el archivo del número existan para el modo de prueba
        const codeFolderPath = path.join(__dirname, CODE_FOLDER);
        try {
            await fs.mkdir(codeFolderPath, { recursive: true });
            const codeFilePath = path.join(codeFolderPath, `${phoneNumber}.txt`);
            await fs.writeFile(codeFilePath, '', 'utf-8');
            console.log(`[INFO] Archivo de código vacío creado para ${phoneNumber} en ${CODE_FOLDER}.`);
        } catch (fileError) {
            console.error(`[ERROR] No se pudo crear el archivo de código para ${phoneNumber}:`, fileError);
            return;
        }

    } else {
        // Operación normal: leer desde results.txt
        simsToProcess = await readSimData();
        if (simsToProcess.length === 0) {
            console.error("[ERROR] No se encontraron números para procesar en 'results.txt'. Abortando.");
            return;
        }
    }
    console.log(`[INFO] Se procesarán ${simsToProcess.length} número(s).`);

    let driver;
    try {
        console.log("[INFO] Conectando al servidor de Appium...");
        let connected = false;
        
        // Limpiamos los datos de la app para el *primer dispositivo* ANTES de intentar conectar Appium.
        // Esto es crucial para un entorno multi-node donde cada worker de Node.js
        // procesará un número a la vez en su dispositivo asignado.
        if (simsToProcess.length > 0 && simsToProcess[0].deviceSerial) {
            await clearAppData(simsToProcess[0].deviceSerial, TELEGRAM_PACKAGE_NAME);
        } else if (simsToProcess.length === 0) {
            console.error("[CRÍTICO] No hay números ni serial de dispositivo para iniciar Appium. Abortando.");
            return;
        }


        for (let i = 0; i < 5; i++) { // 5 intentos de conexión inicial a Appium
            try {
                // Para entornos multi-nodo donde cada worker de Node.js maneja un dispositivo específico
                // ES CRUCIAL que Appium sepa a qué dispositivo conectarse.
                // Aunque tu código original no lo incluía, para múltiples nodos funcionando *independientemente*,
                // Appium necesita el UDID del dispositivo en sus capacidades.
                const currentDeviceSerial = simsToProcess[0].deviceSerial; // Asume que el worker procesará este dispositivo
                const sessionCapabilities = { ...APPIUM_OPTIONS.capabilities };
                if (currentDeviceSerial && currentDeviceSerial !== 'N/A') {
                    sessionCapabilities['appium:udid'] = currentDeviceSerial;
                    console.log(`[INFO] Intentando conectar a Appium con UDID: ${currentDeviceSerial}`);
                }
                
                driver = await remote({ ...APPIUM_OPTIONS, capabilities: sessionCapabilities });
                connected = true;
                console.log("[INFO] Conexión exitosa a Appium.");
                break;
            } catch (err) {
                console.error(`[ERROR] Intento ${i + 1} de conexión a Appium fallido: ${err.message}`);
                await new Promise(resolve => setTimeout(resolve, 5000));
            }
        }
        if (!connected) {
            console.error("[CRÍTICO] No se pudo conectar a Appium después de varios intentos. Abortando.");
            // Si Appium no se conecta, marcamos los números como UNKNOWN
            for (const sim of simsToProcess) {
                 await saveResult(sim, 'UNKNOWN');
                 await cleanupPhoneNumberFile(sim.phoneNumber);
            }
            return;
        }
        
        for (let i = 0; i < simsToProcess.length; i++) {
            const currentSim = simsToProcess[i];
            const phoneNumber = currentSim.phoneNumber;
            const deviceSerial = currentSim.deviceSerial; 
            console.log(`\n--- [${i + 1}/${simsToProcess.length}] Iniciando procesamiento para: ${phoneNumber} ---`);
            
            try {
                // Limpiar datos de la app para cada número procesado. 
                // Esto es vital para asegurar que cada nuevo número tenga una sesión limpia en Telegram.
                // Se hace *después* de la conexión Appium, pero *antes* de interactuar con Telegram para este número.
                await clearAppData(deviceSerial, TELEGRAM_PACKAGE_NAME);

                // Lógica de reseteo robusta y activación de la app
                const phoneScreenIdentifier = '//android.widget.TextView[@text="Tu número de teléfono"]';
                const startScreenIdentifier = '//android.widget.TextView[@text="Empezar a chatear"]';
                
                let onCorrectScreen = false;
                for(let retries = 0; retries < 5 && !onCorrectScreen; retries++) { // 5 reintentos para la pantalla inicial
                    try {
                        const currentPackage = await driver.getCurrentPackage();
                        if (currentPackage !== TELEGRAM_PACKAGE_NAME) {
                            console.log("[INFO] Telegram no está en primer plano, activando app...");
                            await driver.activateApp(TELEGRAM_PACKAGE_NAME);
                            await driver.pause(5000);
                        }

                        if (await driver.$(phoneScreenIdentifier).isExisting({ timeout: 3000 })) {
                            onCorrectScreen = true;
                            console.log("[INFO] En pantalla 'Tu número de teléfono'.");
                        } 
                        else if (await driver.$(startScreenIdentifier).isExisting({ timeout: 3000 })) {
                            console.log("[INFO] En pantalla 'Empezar a chatear', haciendo clic...");
                            await driver.$(startScreenIdentifier).click();
                            await driver.pause(3000);
                            if (await driver.$(phoneScreenIdentifier).isExisting({ timeout: 3000 })) {
                                onCorrectScreen = true;
                                console.log("[INFO] Transición exitosa a pantalla de número.");
                            }
                        } 
                        else {
                            console.log(`[INFO] No en pantalla esperada. Intentando 'back' (${retries + 1}/5)...`);
                            await driver.back();
                            await driver.pause(2000);
                        }
                    } catch (navError) {
                        console.warn(`[ADVERTENCIA][${phoneNumber}] Error durante la navegación inicial (${retries + 1}/5): ${navError.message}`);
                        await driver.pause(2000);
                    }
                }
                if (!onCorrectScreen) {
                    console.error(`[ERROR][${phoneNumber}] No se pudo volver a la pantalla de introducir número después de varios intentos. Saltando este número.`);
                    await saveResult(currentSim, 'UNKNOWN');
                    await cleanupPhoneNumberFile(phoneNumber);
                    continue;
                }

                // Limpieza de campos segura
                const countryCodeInput = await driver.$('//android.widget.EditText[1]');
                const phoneInput = await driver.$('//android.widget.EditText[2]');
                await countryCodeInput.waitForExist({ timeout: 10000 });
                await phoneInput.click();
                for (let k = 0; k < 15; k++) { await driver.sendKeyEvent('67'); } // <-- CORREGIDO: keycode como string
                
                // Introducción de número
                const countryCode = phoneNumber.substring(0, 2);
                const nationalNumber = phoneNumber.substring(2);
                await countryCodeInput.setValue(countryCode);
                await phoneInput.setValue(nationalNumber);

                // Clic en el botón de continuar
                await driver.$('//android.widget.FrameLayout[@content-desc="Listo"]/android.view.View').click();
                await driver.$('//android.widget.TextView[@text="Sí"]').waitForExist({ timeout: 10000 });
                await driver.$('//android.widget.TextView[@text="Sí"]').click();
                
                // Espera de resultados...
                const codeScreen = await driver.$('//android.widget.TextView[@text="Pon el código"]');
                const suspendedPopup = await driver.$('//android.widget.TextView[contains(@text, "suspendido")]');
                const passwordScreen = await driver.$('//android.widget.TextView[@text="Tu contraseña"]');
                const emailScreen = await driver.$('//android.widget.TextView[@text="Elige un correo de acceso"]');
                const tooManyTriesScreen = await driver.$('//android.widget.TextView[contains(@text, "demasiados intentos")]');

                const firstElementTimeout = 30000; // 30 segundos
                const firstElement = await Promise.race([
                    codeScreen.waitForExist({ timeout: firstElementTimeout }).then(() => 'code'),
                    suspendedPopup.waitForExist({ timeout: firstElementTimeout }).then(() => 'suspended'),
                    passwordScreen.waitForExist({ timeout: firstElementTimeout }).then(() => 'password_direct'),
                    emailScreen.waitForExist({ timeout: firstElementTimeout }).then(() => 'email'),
                    tooManyTriesScreen.waitForExist({ timeout: firstElementTimeout }).then(() => 'too_many_attempts')
                ]).catch(err => {
                    console.error(`[ERROR][${phoneNumber}] Ninguna pantalla esperada apareció en ${firstElementTimeout / 1000} segundos: ${err.message}`);
                    return 'timeout_error';
                });
                
                let status = 'UNKNOWN';
                if (firstElement === 'suspended') {
                    await driver.$('//android.widget.Button[@text="OK"]').click();
                    status = 'SUSPENDED';
                } else if (firstElement === 'too_many_attempts') {
                    await driver.$('//android.widget.Button[@text="OK"]').click();
                    status = 'TOO_MANY_ATTEMPTS';
                } else if (firstElement === 'password_direct' || firstElement === 'email') {
                    status = '2FA';
                } else if (firstElement === 'code') {
                    const code = await waitForTelegramCode(phoneNumber);
                    if (code) {
                        await driver.keys(code.split(''));
                        await driver.pause(5000);
                        const finalPasswordField = await driver.$('//android.widget.TextView[@text="Tu contraseña"]');
                        status = (await finalPasswordField.isExisting({ timeout: 10000 })) ? '2FA' : 'NO_2FA';
                    } else {
                        console.error(`[ERROR][${phoneNumber}] waitForTelegramCode devolvió nulo. Considerado UNKNOWN.`);
                        status = 'UNKNOWN';
                    }
                } else if (firstElement === 'timeout_error') {
                    status = 'UNKNOWN';
                }

                await saveResult(currentSim, status);
                await cleanupPhoneNumberFile(phoneNumber);

            } catch (error) {
                console.error(`[ERROR][${phoneNumber}] Error general durante el procesamiento del número: ${error.message}`);
                await saveResult(currentSim, 'UNKNOWN');
                await cleanupPhoneNumberFile(phoneNumber);
                console.log(`[INFO][${phoneNumber}] Intentando reiniciar la app para el siguiente número para asegurar un estado limpio...`);
                try {
                    await driver.terminateApp(TELEGRAM_PACKAGE_NAME);
                    await driver.pause(3000);
                    await driver.activateApp(TELEGRAM_PACKAGE_NAME);
                    await driver.pause(5000);
                } catch (restartError) {
                    console.error(`[ERROR][${phoneNumber}] Fallo crítico al intentar reiniciar la app: ${restartError.message}`);
                }
            }
             console.log(`--- [INFO] Finalizado procesamiento para: ${phoneNumber} ---`);
        }
    } catch (error) {
        console.error(`[ERROR] Ha ocurrido un error fatal en la sesión de Appium o en el bucle principal de procesamiento: ${error.message}`);
    } finally {
        if (driver) {
            console.log("[INFO] Cerrando la sesión de Appium.");
            await driver.deleteSession();
        }
    }
}

main();

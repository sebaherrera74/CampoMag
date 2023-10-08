/*=====[Nombre del programa]===================================================
 * Copyright YYYY Nombre completo del autor <author@mail.com>
 * All rights reserved.
 * Licencia: Texto de la licencia o al menos el nombre y un link
         (ejemplo: BSD-3-Clause <https://opensource.org/licenses/BSD-3-Clause>)
 *
 * Version: 0.0.0
 * Fecha de creacion: YYYY/MM/DD
 */


/*=====[Inclusiones de dependencias de funciones]============================*/


#include "sapi.h"





static char* itoa(int value, char* result, int base);

/*=====[Macros de definición de constantes privadas]=========================*/


/*=====[Definiciones de variables globales externas]=========================*/


/*=====[Definiciones de variables globales publicas]=========================*/


/*=====[Definiciones de variables globales privadas]=========================*/
static volatile float valorVoltaje;
static volatile float campomaggaus;
static volatile float valorAnalogico;

/*=====[Funcion principal, punto de entrada al programa luegp de encender]===*/

int main (void){

	// Inicializar y configurar la plataforma
	boardConfig();
	uartConfig( UART_USB, 115200 );
	adcConfig( ADC_ENABLE ); /* ADC */
	delay( LCD_STARTUP_WAIT_MS );   // Wait for stable power (some LCD need that)

	// Inicializar LCD de 16x2 (caracteres x lineas) con cada caracter de 5x2 pixeles
	lcdInit( 16, 2, 5, 8 );
	lcdGoToXY( 0, 0 ); // Poner cursor en 0, 0
	lcdSendStringRaw( "Campo Magnetico");
	delay(3000);

	lcdClear(); // Borrar la pantalla
	static volatile uint16_t muestra[1024];

	static char uartBuff[10];
	static char uartBuff2[10];
	static volatile uint16_t muestra2[1024];


	uint32_t i,total=0;
	float promedio=0;
	delay_t delay1;
	uint8_t valor=0;
	delayConfig( &delay1, 500 );

	// Saco u  promedio aqui para obtener un valor de tension sin aplicacion de
	//campo magnetico
	for (i=0;i<1024;i++){
		muestra2[i]=adcRead( CH1 );
		total=muestra2[i]+total;
	}
	promedio=total/1024;
	valorAnalogico=(3.3/1024)*promedio;


	while(TRUE) {


		total=0;
		promedio=0;

		valor=!gpioRead( TEC4 );
		if(valor){
			 gpioWrite( LED3, valor );
			 for (i=0;i<1024;i++){
			 		muestra2[i]=adcRead( CH1 );
			 		total=muestra2[i]+total;
			 	}
			 	promedio=total/1024;
			 	valorAnalogico=(3.3/1024)*promedio;

		}


		if ( delayRead( &delay1 ) ){
					lcdClear(); // Borrar la pantalla

					/* Leo la Entrada Analogica AI0 - ADC0 CH1 */
					//muestra = adcRead( CH1 );
					//valorVoltaje=((muestra*3.3)/1023);

					for (i=0;i<1024;i++){
						muestra[i]=adcRead( CH1 );
						total=muestra[i]+total;
					}
					promedio=total/1024;
					valorVoltaje=((promedio*3.3)/1024);
					//Aqui tendria que armar la ecuacion del campo magnetico

					campomaggaus= (valorVoltaje-valorAnalogico)/0.0013;

					floatToString(  campomaggaus, uartBuff2, 2 );
					/* Envío la primer parte del mnesaje a la Uart */
					uartWriteString( UART_USB, "ADC CH1 value: " );

					/* Conversión de muestra entera a ascii con base decimal */
					//itoa( muestra, uartBuff, 10 ); /* 10 significa decimal */

					/* Enviar muestra y Enter */
					//uartWriteString( UART_USB, uartBuff );
					//uartWriteString( UART_USB, ";\r\n" );
					lcdGoToXY( 0, 0 );
					lcdSendStringRaw( uartBuff2 );
					lcdSendStringRaw( "  Gauss" );
				}
	}
	// NO DEBE LLEGAR NUNCA AQUI, debido a que a este programa se ejecuta
	// directamenteno sobre un microcontrolador y no es llamado por ningun
	// Sistema Operativo, como en el caso de un programa para PC.
	return 0;

}



/**
 * C++ version 0.4 char* style "itoa":
 * Written by Lukás Chmela
 * Released under GPLv3.

 */
char* itoa(int value, char* result, int base) {
	// check that the base if valid
	if (base < 2 || base > 36) { *result = '\0'; return result; }

	char* ptr = result, *ptr1 = result, tmp_char;
	int tmp_value;

	do {
		tmp_value = value;
		value /= base;
		*ptr++ = "zyxwvutsrqponmlkjihgfedcba9876543210123456789abcdefghijklmnopqrstuvwxyz" [35 + (tmp_value - value * base)];
	} while ( value );

	// Apply negative sign
	if (tmp_value < 0) *ptr++ = '-';
	*ptr-- = '\0';
	while(ptr1 < ptr) {
		tmp_char = *ptr;
		*ptr--= *ptr1;
		*ptr1++ = tmp_char;
	}
	return result;
}




















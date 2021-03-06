#!/usr/bin/env python
import argparse
from app import Base, engine, connection, Player, Session
import socket
from threading import Thread, Lock
import atexit
import time
from sqlite3 import IntegrityError
import traceback
import sys
import os
import logging
import subprocess

logging.basicConfig(
    filename='syslog.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s'
)


class ClientThread(Thread):
    """A thread that is created for each client from ListenForUsersThread."""
    def __init__(self, ip, port, conn):
        logging.info("Client thread init")
        Thread.__init__(self)
        self.ip = ip
        self.alias = None
        self.port = port
        self.conn = conn
        print(
            "[+] New server socket thread started for " +
            ip + ":" + str(port), flush=True
        )
        self.exception = None

    def run(self):
        """Main functionality of ClientThread"""
        while True:
            try:
                data = self.conn.recv(1024)
                if data:
                    logging.info("Client thread received data %s", data)
                    print(data.decode(), flush=True)
                    rpsgame = RPSGame()
                    data = rpsgame.handle_message(data, self.ip)

            except OSError:
                logging.exception("OSerror in client thread")
                self.conn.close()

            except ConnectionResetError:
                logging.exception("ConnectionReset happened")
                print("session disconnected by player", flush=True)

            except Exception as e:
                logging.exception("Unhandled exception in client thread for ip %s" % self.ip)
                self.exception = e
                print("exception in client thread", flush=True)
                print(e, flush=True)
                traceback.print_exc()
                sys.stdout.flush()

    def send_round_results(self, round_results):
        """Send round results to clients"""
        try:
            self.conn.send(round_results.encode())
            logging.info("Sending results to %s", self.ip)
            print("Sent round results: to", flush=True)
            print([round_results])
            print(round_results, flush=True)
        except OSError:
            logging.exception("OSError in client thread")
            self.conn.close()

    def send_countdown(self, time):
        """Send """
        try:
            self.conn.send(f"Countdown; {time}".encode())
        except OSError:
            logging.exception("OSError in client thread")
            self.conn.close()

    def get_exception(self):
        return self.exception




class ListenForUsersThread(Thread):
    """
    Listens for TCP connections and assigns a ClientThread for the
    incoming connection
    """
    def __init__(self, tcp_server):
        self.tcp_server = tcp_server
        self.exception = None
        Thread.__init__(self)
        logging.info("Init ListenForUserThread")
        print("[+] New server socket thread started for listening for users", flush=True)

    def run(self):
        while True:
            try:
                self.tcp_server.listen(20)
                print("Multithreaded Python server : Waiting for connections from TCP clients...", flush=True)
                (conn, (ip, port)) = self.tcp_server.accept()
                newthread = ClientThread(ip, port, conn)
                newthread.start()
                logging.info("New client thread started for %s", ip)
                threads.append(newthread)
                client_threads.append(newthread)

            except Exception as e:
                self.exception = e
                logging.exception("Exception in ListenForUsersThread")
                print("exception in ListenForUserThread", flush=True)

    def get_exception(self):
        return self.exception


class TimerThread(Thread):
    """
    Acts as the the game round's main clock and sends countdown to
    client threads.
    """
    def __init__(self):
        Thread.__init__(self)
        self.time = 30
        self.round_over = False
        self.exception = None
        print("Timer thread started", flush=True)
        logging.info("init TimerThread")

    def run(self):
        '''sends timer in 10 sec periods'''
        while(1):
            try:
                while not self.round_over:
                    time.sleep(1)
                    self.time = self.time - 1
                    try:
                        for thread in client_threads:
                            thread.send_countdown(self.time)
                    except BrokenPipeError:
                        print("pipe broken for client, closing its socket")
                        logging.exception("BrokenPipeError exception")
                        thread.conn.close()
                    if self.time % 5 == 0:
                        print(f"Time left:{self.time}", flush=True)
                    if self.time <= 0:
                        self.round_over = True

            except Exception as e:
                print("exception in timer thread", flush=True)
                self.exception = e
                logging.exception("TimerThread exception")
                traceback.print_exc()
                sys.stdout.flush()

    def get_exception(self):
        return self.exception


class RPSGame():
    """Server for RPS game"""
    def __init__(self):
        '''Start server'''
        logging.info("RPSGame init")
        pass

    def calculate_results(self):
        '''calculates round results and updates the results to database'''
        global round_results
        global total_points
        total_points = {}
        session = Session()

        # get all players from the database
        for alias, score in session.query(Player.username, Player.player_id):
            # get info from the round's answers
            for index, (round_alias, answer) in enumerate(round_answers):
                if alias == round_alias:
                    print(alias, score)
                    other_answers = round_answers.copy()
                    other_answers = other_answers[:index] + other_answers[index+1:]
                    points = 0
                    for (other_alias, other_answer) in other_answers:
                        if answer == "rock" and other_answer == "scissors":
                            points += 1
                        elif answer == "paper" and other_answer == "rock":
                            points += 1
                        elif answer == "scissors" and other_answer == "paper":
                            points += 1
                        else:
                            # if tie or loss
                            points += 0

                    player = session.query(Player).filter(Player.username == alias).one()
                    print(player.username)
                    print(player.player_score)

                    total_points[str(player.username)] = int(player.player_score)
                    player.player_score += points
                    session.commit()

        results_table = ', '.join("{!s}: {!r}".format(key, val) for (key, val) in total_points.items())
        round_results = str("Outcome; " + results_table)
        print(round_results, flush=True)
        print(results_table, flush=True)
        logging.info(round_results)
        logging.info("total points for last rounds active players: %s", total_points)


    def handle_message(self, message, ip_address):
        '''Handles message received from a client thread'''
        message = message.decode()
        session = Session()
        try:
            message = message.split(";")
            message = [datapair.split(":") for datapair in message]
            message = [[value.strip() for value in sublist] for sublist in message]
            data = {str(sublist[0]): str(sublist[1]) for sublist in message}
            if "msgtype" in data:
                if data["msgtype"] == "connect":
                    player = session.query(Player).filter_by(username=data["alias"]).first()
                    if not player:
                        player = Player(username=data["alias"], ip=ip_address)
                        session.add(player)
                        session.commit()
                        logging.info("Connect type msg received from %s", ip_address)

                        return "connect type msg received"

                if data["msgtype"] == "play":
                    round_answers.append((data["alias"], data["answer"]))
                    logging.info("play type msg received from %s", ip_address)
                    return "play type msg"

        except KeyError:
            print("Missing fields in clients message", flush=True)
            logging.exception("KeyError in RPSGame for ip %s", ip_address)

        except IndexError as e:
            print(e, flush=True)
            logging.exception("IndexError in RPSGame for ip %s", ip_address)
            return "Wrong message fields"

        except IntegrityError:
            print("integrityerror in db")
            logging.exception("IntegrityError RPSGame for ip %s", ip_address)
        except Exception as e:
            print(" error", flush=True)
            print(e, flush=True)
            logging.exception("Exception in RPSGame for ip %s", ip_address)
            return "error in msg"


def main_loop(tcp_ip, tcp_port):
    """main loop of the app. Contains the main game engine"""
    global tcp_server
    tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_server.bind((tcp_ip, int(tcp_port)))
    logging.info("tcp_server ready")

    # Start timer
    global threads
    global client_threads
    global round_answers
    global round_results
    global total_points
    round_answers = []
    client_threads = []
    round_results = "OK"
    total_points = {}
    threads = []
    rps_game = RPSGame()
    timer_thread = TimerThread()
    timer_thread.start()
    listen_thread = ListenForUsersThread(tcp_server)
    listen_thread.start()
    threads.append(timer_thread)
    threads.append(listen_thread)
    is_running = True
    while is_running:
        if timer_thread.round_over:
            logging.info("Round ends")
            rps_game.calculate_results()
            print("Here are the round answers:", flush=True)
            print(round_answers)
            print("Here are the total points:", flush=True)
            print(total_points)
            print("Here is the round results string:", flush=True)
            print(round_results)
            for thread in client_threads:
                logging.info("Send round results to client")
                thread.send_round_results(round_results)
            timer_thread.round_over = False
            timer_thread.time = 30
            round_answers = []


def close_socket():
    tcp_server.close()


if __name__ == "__main__":
    """rooms, lock
    Start a game server
    """
    logging.info("System started, parsing args")
    parser = argparse.ArgumentParser(description='Server of RPS')

    parser.add_argument('--TCP_PORT',
                        dest='tcp_port',
                        help='Own tcp port',
                        default=5005)
    args = parser.parse_args()

    logging.info("args parsed")
    atexit.register(close_socket)
    logging.info("Entering main loop")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(("8.8.8.8", 80))
    host_ip = sock.getsockname()[0]
    print(host_ip)
    logging.info("IP broadcast subprocess starting")
    path = os.path.join(os.path.dirname(__file__), "../sunshine2/sunshine2/bin/Debug/sunshine2.exe")
    subprocess.Popen([path])
    main_loop(host_ip, args.tcp_port)
